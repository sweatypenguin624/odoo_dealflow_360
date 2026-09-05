import argparse
import pandas as pd
import numpy as np
import os
import json
import xgboost as xgb
from sklearn.metrics import roc_auc_score, precision_score, recall_score
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def train_model():
    parser = argparse.ArgumentParser(description="Train XGBoost Recommendation Model")
    parser.add_argument('--device', type=str, default='cuda', choices=['cpu', 'cuda'], help="Device to use for training")
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'data')
    models_dir = os.path.join(base_dir, '..', 'models')
    os.makedirs(models_dir, exist_ok=True)
    
    train_path = os.path.join(data_dir, 'ml_training.csv')
    val_path = os.path.join(data_dir, 'ml_validation.csv')
    
    if not os.path.exists(train_path) or not os.path.exists(val_path):
        logger.error("Training data not found. Run build_training_data.py first.")
        return
        
    logger.info("Loading training and validation data...")
    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path)
    
    logger.info(f"Loaded {len(train_df)} training rows and {len(val_df)} validation rows.")
    
    target_col = 'target'
    
    # Identify categorical columns
    cat_cols = ['recommendation_type', 'customer_tier', 'current_product_id', 'candidate_product_id', 'customer_id']
    
    for col in cat_cols:
        if col in train_df.columns:
            all_cats = pd.concat([train_df[col], val_df[col]]).unique()
            train_df[col] = pd.Categorical(train_df[col], categories=all_cats)
            val_df[col] = pd.Categorical(val_df[col], categories=all_cats)
            
    # Drop target from features
    feature_cols = [c for c in train_df.columns if c != target_col]
    
    X_train = train_df[feature_cols]
    y_train = train_df[target_col]
    X_val = val_df[feature_cols]
    y_val = val_df[target_col]
    
    # Configure XGBoost
    params = {
        'n_estimators': 300,
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'enable_categorical': True,
        'random_state': 42,
        'early_stopping_rounds': 20,
        'eval_metric': 'auc'
    }
    
    if args.device == 'cuda':
        # Check if CUDA is actually available by probing xgboost
        try:
            # simple check
            params['tree_method'] = 'hist'
            params['device'] = 'cuda'
        except Exception:
            logger.warning("CUDA setup failed, falling back to CPU")
            args.device = 'cpu'
            
    if args.device == 'cpu':
        params['tree_method'] = 'hist'
        params['device'] = 'cpu'
        
    print(f"Using GPU: {args.device == 'cuda'}")
    
    model = xgb.XGBClassifier(**params)
    
    logger.info("Training XGBoost model...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_val, y_val)],
        verbose=10
    )
    
    # Save Model
    model_path = os.path.join(models_dir, 'recommendation_model.json')
    model.save_model(model_path)
    logger.info(f"Saved model to {model_path}")
    
    # Save Feature Columns
    features_path = os.path.join(models_dir, 'feature_columns.json')
    with open(features_path, 'w') as f:
        json.dump({'features': feature_cols}, f, indent=4)
        
    logger.info(f"Saved feature columns to {features_path}")
    
    # Calculate basic validation metrics
    preds_proba = model.predict_proba(X_val)[:, 1]
    preds_bin = model.predict(X_val)
    
    try:
        auc_score = roc_auc_score(y_val, preds_proba)
    except ValueError:
        auc_score = 0.0 # Can happen if only 1 class in validation
        
    prec_score = precision_score(y_val, preds_bin, zero_division=0)
    rec_score = recall_score(y_val, preds_bin, zero_division=0)
    
    # Save Metadata
    metadata_path = os.path.join(models_dir, 'model_metadata.json')
    metadata = {
        'training_rows': len(train_df),
        'validation_rows': len(val_df),
        'training_date_range': 'Unknown', # Since invoice date wasn't exported, leaving as placeholder
        'validation_date_range': 'Unknown',
        'feature_names': feature_cols,
        'model_parameters': params,
        'validation_metrics': {
            'roc_auc': auc_score,
            'precision': prec_score,
            'recall': rec_score
        }
    }
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)
        
    logger.info(f"Saved model metadata to {metadata_path}")
    
if __name__ == "__main__":
    train_model()
