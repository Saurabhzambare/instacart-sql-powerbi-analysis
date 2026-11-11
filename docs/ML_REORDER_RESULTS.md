# Instacart reorder prediction results

## Dataset and method

The dataset contains 198,544 customer-product examples from 3,200 labeled
customers. Each customer belongs to one split: 2,240 training, 480 validation,
and 480 test customers.

The frequency baseline ranks products by earlier purchase count, with more
recent purchases ranked first when counts tie. Logistic regression learns from
three historical features: purchase count, share of earlier orders containing
the product, and number of orders since the last purchase.

Both methods selected up to 10 products per order. The cutoff was chosen on
validation before evaluating the held-out test customers.

## Results

| Split | Orders | Frequency mean order F1 | Logistic mean order F1 |
|---|---:|---:|---:|
| Validation | 480 | 0.312357 | 0.317400 |
| Test | 480 | 0.333644 | 0.342393 |

On the test set, logistic regression found 1,390 of 3,012 actual repeat purchases.
The frequency baseline found 1,352. Both made 4,646 predictions.

Mean order F1 gives each order equal weight and accounts for both missed repeat
purchases and extra guesses. The observed test improvement was +0.008749.

## Intended use and limitations

This offline prototype ranks previously purchased products for a customer's next order. It cannot recommend products outside that customer's purchase history. The evaluation covers the recorded cohort of labeled customers from the public dataset and reports an absolute mean per-order F1 change of 0.008749. No online experiment, adoption, sales lift, or production performance was measured. A deployment decision would need evaluation on a representative future cohort and a plan for new products and customers.

## Reproduce the test comparison

Run from the repository root:

    uv run --with "scikit-learn==1.9.1" python -m scripts.evaluate_ml_test_v1

## Reproduce the model export

Run from the repository root.

```powershell
uv run --with "scikit-learn==1.9.1" python -m scripts.export_ml_reorder_v1
```

The export verifies the held-out scores and saves the fitted pipeline,
29,734 candidate predictions, and metrics under `logs/ml_reorder_v1/`.
For another export, pass `--output-dir logs/ml_reorder_v1_repeat`.

[Verified test metrics](validation_evidence/ml_reorder_v1_test_metrics.json)
