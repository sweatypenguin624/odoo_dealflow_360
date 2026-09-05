import pandas as pd
import numpy as np
from mlxtend.frequent_patterns import apriori, association_rules
import logging
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)

def generate_cross_sell_rules(
    invoice_items: pd.DataFrame,
    products: pd.DataFrame,
    min_support: float = 0.005,
    min_confidence: float = 0.10,
    min_lift: float = 1.0
) -> Tuple[pd.DataFrame, Dict]:
    """
    Generates cross-sell rules using Apriori algorithm.
    
    Args:
        invoice_items: DataFrame containing invoice line items.
        products: DataFrame containing product details.
        min_support: Minimum support threshold for Apriori.
        min_confidence: Minimum confidence threshold for association rules.
        min_lift: Minimum lift threshold for association rules.
        
    Returns:
        A tuple containing:
        - pd.DataFrame containing the generated cross-sell rules.
        - Dict containing statistics about the generation process.
    """
    # Data Quality: Handle missing / invalid data
    initial_items_count = len(invoice_items)
    
    # Drop rows with missing invoice_id or product_id
    items_clean = invoice_items.dropna(subset=['invoice_id', 'product_id']).copy()
    
    # Ensure quantity is numeric and valid
    items_clean['quantity'] = pd.to_numeric(items_clean['quantity'], errors='coerce')
    items_clean = items_clean.dropna(subset=['quantity'])
    items_clean = items_clean[items_clean['quantity'] > 0]
    
    if len(items_clean) < initial_items_count:
        logger.warning(f"Discarded {initial_items_count - len(items_clean)} invalid rows from invoice_items.")
        
    # Drop products with missing names
    products_clean = products.dropna(subset=['product_id', 'product_name']).copy()
    
    # Merge items with products to get human-readable product names
    merged_df = items_clean.merge(products_clean[['product_id', 'product_name']], on='product_id', how='inner')
    
    stats = {
        'num_frequent_itemsets': 0,
        'num_association_rules': 0,
        'num_one_to_one_rules': 0
    }
    
    if merged_df.empty:
        logger.warning("Merged dataframe is empty. Check if product IDs match between invoice_items and products.")
        return pd.DataFrame(), stats

    # Build Transaction Baskets
    # Group by invoice_id and product_name, then create a matrix
    basket = (merged_df
              .groupby(['invoice_id', 'product_name'])['quantity']
              .sum().unstack(fill_value=0)
              .reset_index().set_index('invoice_id'))
    
    # Convert quantities to boolean 1/0
    # The mlxtend apriori expects boolean values
    basket = basket.map(lambda x: 1 if x > 0 else 0).astype(bool)
    
    if basket.empty:
        logger.warning("Basket matrix is empty.")
        return pd.DataFrame(), stats
        
    # Apriori
    frequent_itemsets = apriori(basket, min_support=min_support, use_colnames=True)
    
    if frequent_itemsets.empty:
        logger.warning(f"No frequent itemsets found with min_support={min_support}")
        return pd.DataFrame(), stats
        
    stats['num_frequent_itemsets'] = len(frequent_itemsets)
        
    # Association Rules
    rules = association_rules(frequent_itemsets, metric="confidence", min_threshold=min_confidence, num_itemsets=len(basket))
    
    if rules.empty:
        logger.warning(f"No association rules found with min_confidence={min_confidence}")
        return pd.DataFrame(), stats
        
    stats['num_association_rules'] = len(rules)
        
    # Filter by lift
    rules = rules[rules['lift'] >= min_lift]
    
    # Remove Useless Rules
    # We want 1-to-1 rules only
    rules['antecedent_len'] = rules['antecedents'].apply(lambda x: len(x))
    rules['consequent_len'] = rules['consequents'].apply(lambda x: len(x))
    
    rules = rules[(rules['antecedent_len'] == 1) & (rules['consequent_len'] == 1)].copy()
    
    stats['num_one_to_one_rules'] = len(rules)
    
    if rules.empty:
        logger.warning("No 1-to-1 rules found.")
        return pd.DataFrame(), stats
        
    # Extract string from frozenset
    rules['source_product'] = rules['antecedents'].apply(lambda x: list(x)[0])
    rules['recommended_product'] = rules['consequents'].apply(lambda x: list(x)[0])
    
    # Remove same product rules (A -> A)
    rules = rules[rules['source_product'] != rules['recommended_product']]
    
    # Calculate Association Score
    # Normalize confidence and lift
    # Simple Min-Max normalization
    if rules['confidence'].max() == rules['confidence'].min():
        norm_conf = rules['confidence'] / rules['confidence'].max() if rules['confidence'].max() > 0 else rules['confidence']
    else:
        norm_conf = (rules['confidence'] - rules['confidence'].min()) / (rules['confidence'].max() - rules['confidence'].min())
        
    if rules['lift'].max() == rules['lift'].min():
        norm_lift = rules['lift'] / rules['lift'].max() if rules['lift'].max() > 0 else rules['lift']
    else:
        norm_lift = (rules['lift'] - rules['lift'].min()) / (rules['lift'].max() - rules['lift'].min())
        
    rules['association_score'] = (0.6 * norm_conf) + (0.4 * norm_lift)
    
    # Select final columns and sort
    final_rules = rules[['source_product', 'recommended_product', 'support', 'confidence', 'lift', 'association_score']]
    final_rules = final_rules.sort_values(by='association_score', ascending=False).reset_index(drop=True)
    
    return final_rules, stats

def get_cross_sell_candidates(
    product_name: str,
    rules: pd.DataFrame,
    top_n: int = 10
) -> List[str]:
    """
    Looks up recommended products for a given source product.
    
    Args:
        product_name: The name of the product to get recommendations for.
        rules: DataFrame containing the generated rules.
        top_n: Maximum number of recommendations to return.
        
    Returns:
        List of recommended product names.
    """
    if rules.empty:
        return []
        
    candidates = rules[rules['source_product'] == product_name]
    candidates = candidates.sort_values(by='association_score', ascending=False)
    
    return candidates['recommended_product'].head(top_n).tolist()
