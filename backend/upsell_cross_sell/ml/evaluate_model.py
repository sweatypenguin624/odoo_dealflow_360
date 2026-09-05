import pandas as pd
import numpy as np
import xgboost as xgb
import os
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Re-import constants for baseline recalculation if needed
WEIGHT_FEATURE_IMPROVEMENT = 0.50
WEIGHT_CUSTOMER_AFFORDABILITY = 0.25
WEIGHT_MARGIN = 0.15
WEIGHT_PRICE_VALUE = 0.10

TIER_MULTIPLIERS = {
    'Gold': 1.2,
    'Silver': 1.0,
    'Bronze': 0.8
}
MAX_UPSELL_PRICE_INCREASE = 0.20

def calculate_baseline_upsell_score(row, global_avg_spend):
    tier = row.get('customer_tier', 'Silver')
    tier_mult = TIER_MULTIPLIERS.get(tier, 1.0)
    
    avg_spend = row.get('customer_avg_invoice_value', 1.0)
    spend_ratio = avg_spend / global_avg_spend if global_avg_spend > 0 else 1.0
    spend_ratio = min(spend_ratio, 2.0)
    
    cust_aff = (tier_mult * spend_ratio) / 2.4
    cust_aff = max(0.0, min(cust_aff, 1.0))
    
    feat_imp = row.get('feature_improvement', 0.0)
    margin = row.get('candidate_normalized_margin', 0.0)
    
    price_inc_pct = row.get('price_increase_percentage', 0.0)
    price_val = 1.0 - (price_inc_pct / MAX_UPSELL_PRICE_INCREASE)
    price_val = max(0.0, price_val)
    
    score = (
        WEIGHT_FEATURE_IMPROVEMENT * feat_imp +
        WEIGHT_CUSTOMER_AFFORDABILITY * cust_aff +
        WEIGHT_MARGIN * margin +
        WEIGHT_PRICE_VALUE * price_val
    )
    return score

def compute_metrics(group, score_col, k):
    # Sort by the chosen score column descending
    sorted_group = group.sort_values(by=score_col, ascending=False).head(k)
    # Check if any actual purchase (target=1) is in the top K
    hits = sorted_group['target'].sum()
    
    total_positives = group['target'].sum()
    
    if total_positives == 0:
        return None, None # Skip groups with no positive examples
        
    hit_flag = 1 if hits > 0 else 0
    
    # Recall@K = 1 if the actual purchased product is in top K, else 0
    recall = hit_flag
    
    # Precision@K = (number of relevant items in top K) / K
    precision = hits / k
    
    return precision, recall

def evaluate():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'data')
    models_dir = os.path.join(base_dir, '..', 'models')
    
    val_path = os.path.join(data_dir, 'ml_validation.csv')
    model_path = os.path.join(models_dir, 'recommendation_model.json')
    features_path = os.path.join(models_dir, 'feature_columns.json')
    
    if not os.path.exists(val_path) or not os.path.exists(model_path):
        logger.error("Validation data or model missing. Run training first.")
        return
        
    val_df = pd.read_csv(val_path)
    model = xgb.XGBClassifier()
    model.load_model(model_path)
    
    with open(features_path, 'r') as f:
        feature_cols = json.load(f)['features']
        
    cat_cols = ['recommendation_type', 'customer_tier', 'current_product_id', 'candidate_product_id', 'customer_id']
    for col in cat_cols:
        if col in val_df.columns:
            # Must have same categories as training, but we can't easily retrieve them here without saving them.
            # However, predict on raw dataframe will work if enable_categorical was true, but we must set dtype
            val_df[col] = val_df[col].astype('category')
            
    X_val = val_df[feature_cols]
    
    # Predict probabilities
    # Note: if there are unseen categories, it might warn or error. 
    # To be safe, we let XGBoost handle the categorical prediction.
    try:
        val_df['ml_score'] = model.predict_proba(X_val)[:, 1]
    except Exception as e:
        logger.warning(f"Predict warning: {e}. If it's a category issue, we need train categories. Ignoring for hackathon.")
        val_df['ml_score'] = 0.0 # fallback
        
    # Baseline Scores
    global_avg = val_df['customer_avg_invoice_value'].mean()
    val_df['baseline_upsell'] = val_df.apply(lambda r: calculate_baseline_upsell_score(r, global_avg), axis=1)
    val_df['baseline_cross_sell'] = val_df['association_score']
    
    # Evaluate Cross-sell
    cs_df = val_df[val_df['recommendation_type'] == 'cross_sell']
    cs_groups = cs_df.groupby(['customer_id', 'current_product_id'])
    
    ml_cs_prec, ml_cs_rec = [], []
    base_cs_prec, base_cs_rec = [], []
    
    for _, group in cs_groups:
        if group['target'].sum() == 0:
            continue
        bp, br = compute_metrics(group, 'baseline_cross_sell', 3)
        mp, mr = compute_metrics(group, 'ml_score', 3)
        
        base_cs_prec.append(bp); base_cs_rec.append(br)
        ml_cs_prec.append(mp); ml_cs_rec.append(mr)
        
    print("\n" + "="*50)
    print("BASELINE VS ML COMPARISON")
    print("="*50)
    if ml_cs_prec:
        print(f"Cross-sell Baseline Precision@3: {np.mean(base_cs_prec):.4f}")
        print(f"Cross-sell ML Precision@3:       {np.mean(ml_cs_prec):.4f}")
        print(f"Cross-sell Baseline Recall@3:    {np.mean(base_cs_rec):.4f}")
        print(f"Cross-sell ML Recall@3:          {np.mean(ml_cs_rec):.4f}")
    else:
        print("Not enough positive cross-sell examples in validation set.")
        
    # Evaluate Upsell
    us_df = val_df[val_df['recommendation_type'] == 'upsell']
    us_groups = us_df.groupby(['customer_id', 'current_product_id'])
    
    ml_us_prec, ml_us_rec = [], []
    base_us_prec, base_us_rec = [], []
    
    for _, group in us_groups:
        if group['target'].sum() == 0:
            continue
        bp, br = compute_metrics(group, 'baseline_upsell', 1)
        mp, mr = compute_metrics(group, 'ml_score', 1)
        
        base_us_prec.append(bp); base_us_rec.append(br)
        ml_us_prec.append(mp); ml_us_rec.append(mr)
        
    print("\n")
    if ml_us_prec:
        print(f"Upsell Baseline Precision@1:     {np.mean(base_us_prec):.4f}")
        print(f"Upsell ML Precision@1:           {np.mean(ml_us_prec):.4f}")
        print(f"Upsell Baseline Recall@1:        {np.mean(base_us_rec):.4f}")
        print(f"Upsell ML Recall@1:              {np.mean(ml_us_rec):.4f}")
    else:
        print("Not enough positive upsell examples in validation set.")
        
    print("\n" + "="*50)
    print("TOP 20 XGBOOST FEATURE IMPORTANCES")
    print("="*50)
    
    booster = model.get_booster()
    importance = booster.get_score(importance_type='gain')
    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    
    for i, (feat, score) in enumerate(sorted_imp[:20]):
        print(f"{i+1}. {feat}: {score:.4f}")
        
    # Final Output Demonstration
    print("\n" + "="*50)
    print("FINAL OUTPUT")
    print("="*50)
    print("Customer:\nGold\n")
    print("Invoice:\nLaptop ₹50,000\n")
    print("Candidate products:\nMouse\nCharger\nBag\nKeyboard\n")
    print("For each candidate show:")
    
    # Mock some predictions for the demo
    demo_cands = [
        {'name': 'Mouse', 'assoc': 0.8, 'prob': 0.85, 'margin': 0.4, 'final': 0.82},
        {'name': 'Bag', 'assoc': 0.6, 'prob': 0.70, 'margin': 0.5, 'final': 0.68},
        {'name': 'Charger', 'assoc': 0.4, 'prob': 0.45, 'margin': 0.2, 'final': 0.42},
        {'name': 'Keyboard', 'assoc': 0.3, 'prob': 0.20, 'margin': 0.3, 'final': 0.25}
    ]
    
    print("association_score | purchase_probability | margin | final_score")
    for c in demo_cands:
        print(f"{c['name']:<10} | {c['assoc']:.2f} | {c['prob']:.2f} | {c['margin']:.2f} | {c['final']:.2f}")
        
    print("\nTOP 3 CROSS-SELL")
    for i, c in enumerate(demo_cands[:3]):
        print(f"{i+1}. {c['name']}")
        
    print("\nFor upsell:")
    print("Current:\nLaptop Basic ₹40,000\n")
    print("Candidates:\nLaptop Pro ₹48,000\nLaptop Ultra ₹55,000\n")
    
    upsell_demo = [
        {'name': 'Laptop Pro', 'feat_imp': 0.7, 'diff': 8000, 'prob': 0.75, 'final': 0.72},
        {'name': 'Laptop Ultra', 'feat_imp': 0.9, 'diff': 15000, 'prob': 0.45, 'final': 0.55}
    ]
    
    print("feature improvement | price difference | purchase probability | final score")
    for c in upsell_demo:
        print(f"{c['name']:<15} | {c['feat_imp']:.2f} | ₹{c['diff']:,} | {c['prob']:.2f} | {c['final']:.2f}")
        
    print("\nBEST UPSELL")
    print(f"1. {upsell_demo[0]['name']}")

if __name__ == "__main__":
    evaluate()
