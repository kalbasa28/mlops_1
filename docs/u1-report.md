# U1 report: predictive maintenance pipeline

## What was done

- Training pipeline for machine-failure prediction on AI4I 2020 dataset using random forest model: full reproduction with data versioning and image packaging.
- 12 runs with varying parameters executed by AI agent. Run with highest recall and stable precision on bootstrapped data was chosen as the best overall.
- E4: GCS bucket for DVC 
- E2: training as a kubernetes job

## What failed

- GCS credentials have to be managed manually
- Kubernetes job image has to be pinned by separate commit manually

## Time spent

~8-9hrs total over 2 days with the help of Claude Code
