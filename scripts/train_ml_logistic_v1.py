"""Fit a first reorder model and compare its top 10 on validation."""

from collections import defaultdict
from contextlib import closing
from statistics import mean
from typing import NamedTuple

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


TOP_K = 10


class Candidate(NamedTuple):
    order_id: int
    product_id: int
    purchase_count: int
    last_purchase_order: int
    target_order_number: int
    buy_next: int


def load_candidates(cursor, dataset_split):
    cursor.execute(
        """
        SELECT target_order_id, product_id, prior_purchase_count,
            last_prior_order_number, target_order_number, buy_next
        FROM pipeline_ml.reorder_candidates_v1
        WHERE dataset_split = ?
        ORDER BY target_order_id, product_id;
        """,
        dataset_split,
    )
    return [Candidate(*row) for row in cursor]


def features(row):
    previous_orders = row.target_order_number - 1
    return (
        row.purchase_count,
        row.purchase_count / previous_orders,
        row.target_order_number - row.last_purchase_order,
    )


def evaluate_top_k(rows, scores, k=TOP_K):
    orders = defaultdict(list)
    for row, score in zip(rows, scores, strict=True):
        orders[row.order_id].append((row, score))

    order_f1 = []
    predicted = actual = correct = 0
    for entries in orders.values():
        entries.sort(key=lambda entry: (-entry[1], -entry[0].last_purchase_order, entry[0].product_id))
        selected = entries[:k]
        actual_in_order = sum(row.buy_next for row, _ in entries)
        correct_in_order = sum(row.buy_next for row, _ in selected)
        denominator = actual_in_order + len(selected)
        order_f1.append(2 * correct_in_order / denominator if denominator else 1.0)
        predicted += len(selected)
        actual += actual_in_order
        correct += correct_in_order

    return {
        "orders": len(orders),
        "actual": actual,
        "predicted": predicted,
        "correct": correct,
        "mean_order_f1": mean(order_f1),
    }


def fit_model(training_rows):
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit([features(row) for row in training_rows], [row.buy_next for row in training_rows])
    return model


def main():
    from scripts.db_connection import get_connection

    with closing(get_connection()) as connection, closing(connection.cursor()) as cursor:
        training = load_candidates(cursor, "train")
        validation = load_candidates(cursor, "validation")

    if (len(training), len(validation)) != (139878, 28932):
        raise ValueError("Candidate counts differ from the verified v1 dataset.")

    baseline = evaluate_top_k(validation, [row.purchase_count for row in validation])
    if (
        (baseline["orders"], baseline["actual"], baseline["predicted"], baseline["correct"])
        != (480, 2876, 4669, 1274)
        or abs(baseline["mean_order_f1"] - 0.312357) > 0.000001
    ):
        raise ValueError("The Python frequency baseline differs from the verified SSMS result.")

    model = fit_model(training)
    probabilities = model.predict_proba([features(row) for row in validation])[:, 1]
    logistic = evaluate_top_k(validation, probabilities)
    delta = logistic["mean_order_f1"] - baseline["mean_order_f1"]

    print(f"Training rows: {len(training):,}")
    print(f"Validation rows: {len(validation):,}")
    print(f"Validation orders: {baseline['orders']}")
    print(f"Products predicted per order: up to {TOP_K}")
    print(f"Frequency mean order F1: {baseline['mean_order_f1']:.6f}")
    print(f"Logistic mean order F1:   {logistic['mean_order_f1']:.6f}")
    print(f"F1 difference:          {delta:+.6f}")
    print(f"Logistic correct reorders: {logistic['correct']:,} of {logistic['actual']:,} actual")

    print("\nLogistic validation results by cutoff")
    print("Top K | Mean order F1 | Correct reorders | Predictions")

    results = []
    for k in (1, 3, 5, 10, 15, 20):
        result = evaluate_top_k(validation, probabilities, k=k)
        results.append((k, result["mean_order_f1"]))
        print(
            f"{k:>5} | {result['mean_order_f1']:>13.6f} | "
            f"{result['correct']:>16,} | {result['predicted']:>11,}"
        )

    best_k, best_f1 = max(results, key=lambda item: (item[1], -item[0]))
    print(f"Best validation cutoff: top {best_k} (F1 = {best_f1:.6f})")


if __name__ == "__main__":
    main()
