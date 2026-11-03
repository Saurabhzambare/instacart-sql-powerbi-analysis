from contextlib import closing

from scripts.db_connection import get_connection
from scripts.train_ml_logistic_v1 import (
    evaluate_top_k,
    features,
    fit_model,
    load_candidates,
)


def main():
    with closing(get_connection()) as connection, closing(connection.cursor()) as cursor:
        training = load_candidates(cursor, "train")
        test = load_candidates(cursor, "test")

    if (len(training), len(test)) != (139878, 29734):
        raise ValueError("Row counts differ from the verified v1 dataset.")

    frequency = evaluate_top_k(test, [row.purchase_count for row in test], k=10)
    if (frequency["orders"], frequency["actual"]) != (480, 3012):
        raise ValueError("Test orders or actual reorders differ from the verified split.")

    model = fit_model(training)
    probabilities = model.predict_proba([features(row) for row in test])[:, 1]
    logistic = evaluate_top_k(test, probabilities, k=10)

    print(f"Test orders: {frequency['orders']}")
    print(f"Actual repeat purchases: {frequency['actual']:,}")
    print("Method      | Mean order F1 | Correct reorders | Predictions")

    for name, result in (("Frequency", frequency), ("Logistic", logistic)):
        print(
            f"{name:<11} | {result['mean_order_f1']:>13.6f} | "
            f"{result['correct']:>16,} | {result['predicted']:>11,}"
        )

    difference = logistic["mean_order_f1"] - frequency["mean_order_f1"]
    print(f"Test F1 difference (logistic minus frequency): {difference:+.6f}")


if __name__ == "__main__":
    main()