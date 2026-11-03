# Preview the Instacart ML examples

Prepared: 2 November 2026. Starting checkpoint: `54dd4bb`.

## What we are building

One row asks: "Will this customer buy this previously purchased product in their
next order?" The answer column is called `buy_next`: 1 means yes and 0 means no.

The saved label table contains only actual purchases. It cannot show an absent
product. We therefore start with each customer's earlier purchased products and
look for each one in their target order. A missing match becomes 0.

| Example earlier history | Product in target order? | buy_next |
|---|---|---:|
| Customer bought Banana before | Yes | 1 |
| Customer bought Milk before | No | 0 |

A new product in the target order is outside this initial repeat-purchase task.
It must not be used to expand the candidate list after seeing the answer.

## Run this in SSMS

1. Copy `sql/preview_ml_candidates.sql` into the repository's `sql` folder.
2. Open the file in a new SQL Server Management Studio query tab.
3. Select the database `InstacartAnalytics`.
4. Ensure no text is selected, then execute the entire file with F5.
5. Send the result grids and any error in Messages.

There is no new PowerShell command or Python dependency for this preview.

The script uses only `#mlp_...` session temporary tables. It does not publish,
delete, or update permanent data. Closing the connection removes the temporary
tables. A later run clears only this script's own temporary tables first.

## How it prevents using future answers as history

| Information | Use in this preview |
|---|---|
| Earlier orders marked prior | Candidate products and historical purchase counts |
| Order sequence number | Keep history strictly before the target order |
| Target product presence | Construct buy_next only |
| Target source_reordered | Diagnostic history cross-check only |
| Target cart position | Input validity check only; not a predictor |

The history join requires `prior.order_number < target.order_number`, matches the
same customer, and includes only prior orders. The two displayed history columns
come from earlier orders. `target_order_number` is cutoff metadata, not an
automatically approved predictor. Identifiers also identify rows rather than
automatically becoming model inputs.

The source flag must agree with history reconstructed from the full prior table.
It is not copied into `buy_next`; the target is computed from product presence.

## What the four result grids mean

| Result | Meaning | Expected / observation |
|---|---|---|
| 1 | Total candidate rows and positive/negative distribution | Total and negative counts must be observed live; 3,200 users/orders and 20,229 positives expected after reconciliation |
| 2 | Flag/history disagreement, invalid histories/targets, missing products | All zero |
| 3 | Actual target purchases split by earlier purchase history | 33,782 total; 20,229 repeat entries; 13,553 first purchases excluded |
| 4 | Thirty candidate rows with product names and targets | Inspect actual examples; the first thirty need not contain both target values |

Candidate rows are expected to exceed the 33,782 actual target purchases because
we include historical products not bought in the next order. Do not invent or
freeze the total count until the live preview succeeds.

`positive_rate_pct` means the percentage of candidate examples whose target is 1.
It is not model accuracy; there is no fitted model yet.

## Status and next steps

This preview is not a trained model, a permanent candidate table, or a completed
train/test split. The existing 118-test Python suite is unchanged.

Offline preparation checked the two core SELECT queries on six small fixture
cases: positive/negative examples, strict history cutoff, excluded first purchases,
presence-based targets, unchanged history features when answers change, and
customer/target-order matching. The checks used SQLite adaptations of SELECT INTO
and COUNT_BIG; they do not verify SQL Server syntax, transaction behavior, or the
real dataset. The complete SSMS run remains the acceptance step.

After live inspection, record the measured counts. Then define the reproducible
customer partitions and permanent candidate dataset. Keep every customer's rows
in one partition. Fit any learned preprocessing/model parameters using the
training partition only; choose settings on validation and evaluate once on the
held-out local test partition. The official unlabeled test customers remain
separate from the 3,200 labeled customers used here.

Creating fixed, per-customer historical counts for this preview does not fit
parameters using held-out outcomes. Future cross-customer aggregates, encoders,
scalers, feature selection, and tuning require their own split-aware handling.
