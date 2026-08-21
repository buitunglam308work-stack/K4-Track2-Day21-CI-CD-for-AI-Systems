import mlflow
import mlflow.sklearn
import pandas as pd
import yaml
import json
import joblib
import os
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

# Nguong chat luong cua lab nay la f1_score, KHONG phai accuracy.
# Ly do: bo du lieu Adult co ty le lop 75/25. Mot mo hinh doan bua
# "thu nhap thap" cho moi mau da dat accuracy 0.75 ma khong hoc duoc gi.
F1_THRESHOLD = 0.65


def train(
    params: dict,
    data_path: str = "data/train_batch1.csv",
    eval_path: str = "data/holdout.csv",
) -> float:
    """
    Huan luyen mo hinh va ghi nhan ket qua vao MLflow.

    Tham so:
        params     : dict chua cac sieu tham so cho GradientBoostingClassifier.
        data_path  : duong dan den file du lieu huan luyen.
        eval_path  : duong dan den file du lieu danh gia (holdout).

    Tra ve:
        f1 (float): diem F1 cua lop duong (thu nhap > 50K) tren tap holdout.
    """

    df_train = pd.read_csv(data_path)
    df_eval = pd.read_csv(eval_path)

    X_train = df_train.drop(columns=["target"])
    y_train = df_train["target"]
    X_eval = df_eval.drop(columns=["target"])
    y_eval = df_eval["target"]

    positive_rate = float(y_train.mean())
    reference_rate = 0.248
    if abs(positive_rate - reference_rate) > 0.05:
        print(
            "CANH BAO: ty le lop duong tren tap train "
            f"{positive_rate:.2%} lech qua 5 diem phan tram so voi {reference_rate:.1%}."
        )

    with mlflow.start_run():

        mlflow.log_params(params)

        model = GradientBoostingClassifier(**params, random_state=42)
        model.fit(X_train, y_train)

        preds = model.predict(X_eval)
        f1 = float(f1_score(y_eval, preds))
        acc = float(accuracy_score(y_eval, preds))

        probabilities = model.predict_proba(X_eval)[:, 1]
        thresholds = [round(0.1 + 0.05 * i, 2) for i in range(17)]
        threshold_scores = {
            threshold: float(
                f1_score(y_eval, (probabilities >= threshold).astype(int))
            )
            for threshold in thresholds
        }
        best_threshold = max(threshold_scores, key=threshold_scores.get)
        f1_at_best_threshold = threshold_scores[best_threshold]

        cm = confusion_matrix(y_eval, preds, labels=[0, 1])
        precision_by_class = precision_score(
            y_eval, preds, labels=[0, 1], average=None, zero_division=0
        )
        recall_by_class = recall_score(
            y_eval, preds, labels=[0, 1], average=None, zero_division=0
        )
        detail = (
            "Confusion matrix (rows=true, cols=predicted; labels [0, 1]):\n"
            f"{cm}\n\n"
            "Class metrics:\n"
            f"class 0 (thu_nhap_thap): precision={precision_by_class[0]:.4f}, "
            f"recall={recall_by_class[0]:.4f}\n"
            f"class 1 (thu_nhap_cao): precision={precision_by_class[1]:.4f}, "
            f"recall={recall_by_class[1]:.4f}\n"
        )

        mlflow.log_metric("f1_score", f1)
        mlflow.log_metric("accuracy", acc)
        mlflow.log_metric("best_threshold", float(best_threshold))
        mlflow.log_metric("f1_at_best_threshold", f1_at_best_threshold)
        mlflow.log_metric("positive_rate", positive_rate)
        mlflow.sklearn.log_model(model, "model")

        print(f"F1: {f1:.4f} | Accuracy: {acc:.4f}")
        print(
            f"Best threshold: {best_threshold:.2f} | "
            f"F1 at threshold: {f1_at_best_threshold:.4f}"
        )

        os.makedirs("outputs", exist_ok=True)
        with open("outputs/report.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "f1_score": f1,
                    "accuracy": acc,
                    "best_threshold": float(best_threshold),
                    "f1_at_best_threshold": f1_at_best_threshold,
                    "positive_rate": positive_rate,
                },
                f,
                indent=2,
            )
        with open("outputs/detail.txt", "w", encoding="utf-8") as f:
            f.write(detail)

        os.makedirs("models", exist_ok=True)
        joblib.dump(model, "models/model.joblib")

    return float(f1)


if __name__ == "__main__":
    with open("params.yaml") as f:
        params = yaml.safe_load(f)
    train(params)
