"""Reproduce the held-out comparison and save the verified model run."""

import argparse
import csv
import json
import platform
from contextlib import closing
from importlib.metadata import version
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib

from scripts.train_ml_logistic_v1 import (
    evaluate_top_k,
    features,
    fit_model,
    load_candidates,
)


TOP_K = 10


def write_run(destination, model, test_rows, probabilities, metrics):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temp_dir:
        staging = Path(temp_dir) / "run"
        staging.mkdir()
        joblib.dump(model, staging / "logistic_pipeline.joblib")

        ranked = sorted(
            zip(test_rows, probabilities, strict=True),
            key=lambda pair: (
                pair[0].order_id, -pair[1], -pair[0].last_purchase_order, pair[0].product_id
            ),
        )
        predictions = correct = 0
        with (staging / "test_predictions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "target_order_id", "product_id", "reorder_probability", "rank_in_order",
                "predicted_buy_next", "actual_buy_next",
            ])
            for order_id, candidates in groupby(ranked, key=lambda pair: pair[0].order_id):
                for rank, (row, probability) in enumerate(candidates, start=1):
                    predicted = int(rank <= TOP_K)
                    predictions += predicted
                    correct += predicted * row.buy_next
                    writer.writerow([order_id, row.product_id, float(probability), rank, predicted, row.buy_next])

        if (predictions, correct) != (metrics["logistic"]["predicted"], metrics["logistic"]["correct"]):
            raise ValueError("Exported predictions do not match the evaluated results.")

        (staging / "metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(destination)


def main():
    from scripts.db_connection import get_connection

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("logs/ml_reorder_v1"))
    destination = parser.parse_args().output_dir
    if destination.exists():
        parser.error(f"{destination} already exists. Choose a new --output-dir.")

    with closing(get_connection()) as connection, closing(connection.cursor()) as cursor:
        training = load_candidates(cursor, "train")
        test = load_candidates(cursor, "test")

    if (len(training), len(test)) != (139878, 29734):
        raise ValueError("Row counts differ from the verified candidate dataset.")

    frequency = evaluate_top_k(test, [row.purchase_count for row in test], k=TOP_K)
    model = fit_model(training)
    probabilities = model.predict_proba([features(row) for row in test])[:, 1]
    logistic = evaluate_top_k(test, probabilities, k=TOP_K)

    for result, expected_hits, expected_f1 in (
        (frequency, 1352, 0.333644),
        (logistic, 1390, 0.342393),
    ):
        if (
            (result["orders"], result["actual"], result["predicted"], result["correct"])
            != (480, 3012, 4646, expected_hits)
            or abs(result["mean_order_f1"] - expected_f1) > 0.000001
        ):
            raise ValueError("Reproduced metrics differ from the verified test result.")

    metrics = {
        "source": "pipeline_ml.reorder_candidates_v1",
        "fit_split": "train",
        "evaluated_split": "test",
        "top_k": TOP_K,
        "training_rows": len(training),
        "test_rows": len(test),
        "feature_order": [
            "prior_purchase_count",
            "prior_purchase_count / (target_order_number - 1)",
            "target_order_number - last_prior_order_number",
        ],
        "versions": {
            "python": platform.python_version(),
            **{package: version(package) for package in ("scikit-learn", "joblib", "numpy", "scipy")},
        },
        "frequency": frequency,
        "logistic": logistic,
        "mean_order_f1_gain": logistic["mean_order_f1"] - frequency["mean_order_f1"],
    }
    write_run(destination, model, test, probabilities, metrics)
    print(f"Saved model, {len(test):,} prediction rows, and metrics in {destination}")
    print(f"Test F1: frequency {frequency['mean_order_f1']:.6f}, logistic {logistic['mean_order_f1']:.6f}")


if __name__ == "__main__":
    main()
