# Wine-quality model API operations

## Endpoints
POST /predict scores 1 to 1000 samples. GET /healthz is liveness, GET /readyz is readiness (503 until the model is loaded), GET /metrics/ exposes Prometheus metrics: wine_predictions_total, wine_predict_latency_seconds, wine_predicted_quality.

## Model quality
The production model is a random forest. Held-out test metrics: RMSE 0.598, MAE 0.426, R² 0.532, 69.0% exact grade, 97.4% within one grade. A mean-predictor baseline has RMSE 0.874.

## Drift warning signs
A shift in the wine_predicted_quality histogram (for example most predictions collapsing to 5-6) without a change in traffic suggests input drift. Compare recent feature distributions with the training data before retraining.

## Scaling
The Helm chart runs 2 to 6 replicas with an HPA at 70% CPU; pods run non-root with a read-only root filesystem.
