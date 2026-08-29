# AskCell detection benchmark

Synthetic specimens on a 14-colour B-ALL panel, with a known abnormal fraction. Every specimen also contains hematogones -- normal B-cell precursors whose immunophenotype closely mimics blasts -- so the healthy controls are a genuine test rather than a formality.


## Headline

| Metric | Value |
| --- | --- |
| Limit of detection (deepest acquisition) | 0.01% |
| Mean sensitivity, detected cases | 97.94% |
| Mean precision, detected cases | 100.0% |
| Specificity (healthy controls) | 100.0% (4/4) |
| Reproducible across repeat runs | identical |
| Throughput | 1.55s per 100k events |
| Reference build (one-off) | 16.69s |

## Limit of detection by acquisition depth

The limit is not a property of the software alone. A 0.01% population is ~5 cells in 50,000 and cannot be called by anything; the same fraction is ~50 cells at 500,000 events. Acquiring more events is what buys sensitivity. A population below 30 cells is refused at any depth, because it is not distinguishable from a chance clump of noise.

| Events acquired | Lowest fraction detected | Approx. cells |
| --- | --- | --- |
| 50,000 | 0.1% | ~50 |
| 200,000 | 0.05% | ~100 |
| 500,000 | 0.01% | ~50 |

**The limit is a cell count, not a percentage.** Across a tenfold range of acquisition depth the smallest detectable population stayed at roughly 50-100 cells, while the percentage it corresponds to moved by a factor of ten. The detector needs a certain number of cells to recognise a population as a population; what fraction of the specimen that represents is set by how many events were acquired, not by the software.

The practical consequence: **to lower the detectable percentage, acquire more events.** This is the same tradeoff clinical MRD assays make, and it is why they run millions of events rather than thousands.

## Every run

| Kind | Events | True % | Reported % | Sensitivity | Precision | Detected | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dilution | 50,000 | 5.08274 | 5.0806 | 99.96% | 100.0% | yes | 0.75 |
| dilution | 50,000 | 1.02595 | 1.0238 | 99.79% | 100.0% | yes | 0.67 |
| dilution | 50,000 | 0.09877 | 0.0816 | 82.61% | 100.0% | yes | 0.66 |
| dilution | 50,000 | 0.04938 | 0.0 | 0.0% | — | no | 0.69 |
| dilution | 50,000 | 0.00859 | 0.0 | 0.0% | — | no | 0.69 |
| dilution | 200,000 | 5.11196 | 5.112 | 100.0% | 100.0% | yes | 4.41 |
| dilution | 200,000 | 1.02677 | 1.0246 | 99.79% | 100.0% | yes | 2.77 |
| dilution | 200,000 | 0.10305 | 0.1025 | 99.48% | 100.0% | yes | 2.66 |
| dilution | 200,000 | 0.05153 | 0.0515 | 100.0% | 100.0% | yes | 2.74 |
| dilution | 200,000 | 0.01073 | 0.0 | 0.0% | — | no | 2.67 |
| dilution | 500,000 | 5.10879 | 5.1088 | 100.0% | 100.0% | yes | 18.36 |
| dilution | 500,000 | 1.02216 | 1.0222 | 100.0% | 100.0% | yes | 7.52 |
| dilution | 500,000 | 0.10026 | 0.0992 | 98.93% | 100.0% | yes | 7.19 |
| dilution | 500,000 | 0.04894 | 0.0485 | 99.12% | 100.0% | yes | 7.01 |
| dilution | 500,000 | 0.00988 | 0.0094 | 95.65% | 100.0% | yes | 6.88 |
| specificity | 200,000 | 0.0 | 0.0 | — | — | no | 2.72 |
| specificity | 200,000 | 0.0 | 0.0 | — | — | no | 2.71 |
| specificity | 200,000 | 0.0 | 0.0 | — | — | no | 2.76 |
| specificity | 200,000 | 0.0 | 0.0 | — | — | no | 2.8 |

## Caveats

- Synthetic data. The generator encodes a specific idea of what a blast population looks like, so these numbers measure internal consistency, not clinical accuracy. Real specimens are messier in ways a generator does not know to imitate.
- Not clinically validated. Clinical validation needs hundreds of real cases with confirmed diagnoses and ethical approval.
- One panel. All results are for the 14-colour B-ALL panel above; the detector must be re-characterised for any other panel.
- Research and educational use only. Not a diagnostic device.
