# 14. Line-by-Line Analysis

This section breaks down one of the most complex and critical loops in the repository: generating the training examples for the Upsell Machine Learning model.

## Target: `upsell_cross_sell/ml/build_training_data.py` (Lines 146-219)

This block is inside the main chronological loop over all invoices. Its goal is to create positive and negative examples of "Upsells" to train the XGBoost classifier.

```python
146: for actual_purchased_id in purchased_product_ids:
147:     actual_prod = products[products['product_id'] == actual_purchased_id].iloc[0]
148:     cat = actual_prod['category']
149:     price = actual_prod['selling_price']
```
- **What**: Loops over every product actually bought in the current invoice. It grabs the product's full row from the `products` DataFrame, extracting its `category` and `selling_price`.
- **Why**: To generate an upsell, we need to know what the user *actually* bought, so we can define it as the "Target" (the successful upsell).

```python
151:     # Find a cheaper product in the same category to act as the "base" consideration
152:     cheaper_prods = products[(products['category'] == cat) & (products['selling_price'] < price)]
```
- **What**: Filters the product catalog to find all products in the same category that are cheaper than what the customer actually bought.
- **Why**: An "upsell" implies selling a more expensive version of a base item. Because we only have historical invoice data (we know what they *bought*, but not what they *started looking at*), we must simulate the starting point. We assume they started looking at a cheaper product and were successfully upsold to the `actual_purchased_id`.

```python
154:     if cheaper_prods.empty:
155:         continue
```
- **What**: If there are no cheaper products, skip to the next loop iteration.
- **Why**: If they bought the absolute cheapest item in the category, they were not upsold. We cannot use this as a positive upsell example.

```python
157:     # Pick one cheaper product randomly as the assumed starting point to keep data balanced
158:     base_prod = cheaper_prods.sample(1).iloc[0]
```
- **What**: Randomly selects exactly one of the cheaper products.
- **Why**: Using all cheaper products would flood the training dataset with thousands of identical targets, skewing the model. Random sampling maintains class balance.

```python
160:     # Generate upsell candidates from this base product
161:     candidates_df = recommend_upsell(
162:         customer_id=cust_id,
163:         current_product_ids=[base_prod['product_id']],
164:         products=products,
165:         customers=customers,
166:         top_n=10
167:     )
```
- **What**: Calls the Apriori rules engine (`recommend_upsell`) to ask: "If a user is looking at this cheap `base_prod`, what 10 items would you try to upsell them to?"
- **Why**: We need to generate the "negative" examples. The Apriori engine generates 10 candidates. We know only 1 of them was actually bought (the `actual_purchased_id`). The other 9 will be our "0" targets (failed upsells).

```python
174:     if actual_purchased_id not in candidates_df['recommended_product_id'].values:
175:         continue
```
- **What**: Checks if the item the user *actually* bought is in the list of 10 candidates. If not, it skips the loop.
- **Why**: If the Apriori engine didn't even suggest the item they bought, we have a disconnect. We only want to train the model on scenarios where the candidate *was* shown to the user, and they either accepted or rejected it.

```python
177:     for _, cand in candidates_df.iterrows():
178:         cand_id = cand['recommended_product_id']
179:         target = 1 if cand_id == actual_purchased_id else 0
```
- **What**: Iterates through the 10 candidates. Sets `target = 1` if the candidate matches what the user actually bought, otherwise `0`.
- **Why**: This creates the binary labels that the XGBoost classifier needs to learn.

```python
181:         pop = product_popularity.get(cand_id, 0)
182:         cand_cat = products[products['product_id'] == cand_id].iloc[0].get('category', '')
183:         cand_brand = products[products['product_id'] == cand_id].iloc[0].get('brand', '')
184:         c_aff = cat_affinity.get(cand_cat, 0)
185:         b_aff = brand_affinity.get(cand_brand, 0)
```
- **What**: Fetches historical state features. `product_popularity` tracks how many times the item has been bought *up to this point in time*. `c_aff` and `b_aff` track how many times this specific user has bought this category or brand previously.
- **Why**: These are the features the ML model uses to guess if the user will say yes. If `c_aff` (category affinity) is very high, the user is likely to accept the upsell. **Crucially, these dictionaries are updated *after* the invoice is processed (Line 224), preventing data leakage where the model looks into the future.**

```python
188:         examples.append({
189:             'recommendation_type': 'upsell',
190:             'customer_id': cust_id,
...
218:             'target': target
219:         })
```
- **What**: Appends a massive dictionary of all features and the `target` label to the `examples` list, which is eventually converted into the Pandas DataFrame and saved as a CSV.
