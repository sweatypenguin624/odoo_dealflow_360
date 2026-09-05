#!/usr/bin/env python3
"""
Synthetic Data Generator for Cross-Sell & Upsell Recommendation Engine

Generates realistic B2B electronics invoicing data with hidden purchasing patterns
for Apriori association-rule mining and recommendation ranking.

RESPONSIBILITY: Data generation only.
Does NOT implement Apriori, XGBoost, or recommendation logic.

Usage:
    python generate_data.py
    python generate_data.py --customers 10000 --invoices 50000 --seed 42
"""

import os
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd


class ElectronicsDataGenerator:
    """Generates realistic B2B electronics invoicing data."""

    def __init__(self, num_customers: int = 10000, num_invoices: int = 50000, seed: int = 42):
        self.num_customers = num_customers
        self.num_invoices = num_invoices
        self.seed = seed
        np.random.seed(seed)

        self.products_df = None
        self.customers_df = None
        self.invoices_df = None
        self.invoice_items_df = None

        # Cross-sell patterns: product_category -> {related_product_category: probability}
        self.cross_sell_patterns = {
            "Laptops": {"Mice": 0.70, "Chargers": 0.60, "Laptop Bags": 0.50, "Keyboards": 0.30, "External SSDs": 0.20},
            "Smartphones": {"Chargers": 0.60, "Headphones": 0.35, "USB Hubs": 0.15},
            "Tablets": {"Chargers": 0.60, "Headphones": 0.30, "Keyboards": 0.20},
            "Monitors": {"Keyboards": 0.25, "Mice": 0.30, "USB Hubs": 0.20},
            "Printers": {"Ink Cartridges": 0.75, "Printer Paper": 0.65, "USB Hubs": 0.15},
            "Keyboards": {"Mice": 0.35, "Laptop Bags": 0.10},
            "Mice": {"Keyboards": 0.25, "USB Hubs": 0.10},
        }

    def generate_products(self) -> pd.DataFrame:
        """Generate product catalog with realistic electronics items."""
        products = []
        product_id = 1

        # Product configuration: category -> list of (subcategory, brands, price_range, specs)
        categories_config = {
            "Laptops": [
                ("Entry-Level", ["Dell", "HP", "Lenovo"], (35000, 50000), {"ram": [8, 12], "storage": [256, 512], "processor": ["i3", "Ryzen 5"]}),
                ("Professional", ["Dell", "HP", "Lenovo"], (50000, 75000), {"ram": [16], "storage": [512], "processor": ["i5", "Ryzen 7"]}),
                ("Premium", ["MacBook", "Dell", "Lenovo"], (75000, 120000), {"ram": [16, 32], "storage": [512, 1024], "processor": ["i7", "M1"]}),
            ],
            "Smartphones": [
                ("Budget", ["Xiaomi", "Realme", "Poco"], (12000, 25000), {"ram": [4, 6], "storage": [64, 128]}),
                ("Mid-Range", ["Samsung", "OnePlus", "Xiaomi"], (25000, 50000), {"ram": [6, 8], "storage": [128, 256]}),
                ("Premium", ["iPhone", "Samsung", "OnePlus"], (50000, 100000), {"ram": [8, 12], "storage": [256, 512]}),
            ],
            "Tablets": [
                ("Standard", ["iPad", "Samsung"], (20000, 40000), {"ram": [4, 6], "storage": [64, 128]}),
                ("Pro", ["iPad", "Samsung"], (40000, 80000), {"ram": [6, 8], "storage": [128, 256]}),
            ],
            "Monitors": [
                ("Standard", ["Dell", "LG", "ASUS"], (8000, 20000), {"storage": 0}),
                ("Gaming", ["ASUS", "MSI", "BenQ"], (20000, 60000), {"storage": 0}),
            ],
            "Keyboards": [
                ("Mechanical", ["Corsair", "Razer", "Logitech"], (2000, 8000), {}),
                ("Membrane", ["Logitech", "Dell"], (800, 2000), {}),
            ],
            "Mice": [
                ("Wireless", ["Logitech", "Corsair"], (1000, 3000), {}),
                ("Wired", ["Dell", "Logitech"], (500, 1500), {}),
            ],
            "Laptop Bags": [
                ("Standard", ["Dell", "HP"], (1000, 3000), {}),
                ("Premium", ["Samsonite", "Dell"], (3000, 6000), {}),
            ],
            "Chargers": [
                ("Standard", ["Dell", "HP"], (1000, 2000), {}),
                ("Fast", ["Anker", "Belkin"], (2000, 6000), {}),
            ],
            "USB Hubs": [
                ("Basic", ["Belkin", "Anker"], (800, 2000), {}),
                ("Powered", ["Belkin", "Anker"], (2000, 5000), {}),
            ],
            "Headphones": [
                ("Budget", ["Realme", "Xiaomi"], (1000, 3000), {}),
                ("Premium", ["Sony", "Bose", "Apple"], (5000, 20000), {}),
            ],
            "Webcams": [
                ("Standard", ["Dell", "Logitech"], (2000, 5000), {}),
                ("Professional", ["Logitech", "Razer"], (5000, 15000), {}),
            ],
            "Printers": [
                ("Inkjet", ["HP", "Canon"], (8000, 25000), {}),
                ("Laser", ["HP", "Canon"], (15000, 60000), {}),
            ],
            "Ink Cartridges": [
                ("Standard", ["HP", "Canon"], (500, 2000), {}),
            ],
            "Printer Paper": [
                ("A4", ["ITC", "Paperline"], (200, 800), {}),
            ],
            "External SSDs": [
                ("256GB-512GB", ["Samsung", "WD", "Kingston"], (3000, 8000), {"storage": [256, 512]}),
                ("1TB", ["Samsung", "WD"], (8000, 15000), {"storage": [1024]}),
            ],
        }

        for category, subcategories in categories_config.items():
            for subcat, brands, price_range, specs in subcategories:
                for _ in range(np.random.randint(8, 16)):  # 8-15 products per subcategory
                    cost_price = np.random.uniform(price_range[0] * 0.6, price_range[1] * 0.6)
                    selling_price = np.random.uniform(price_range[0], price_range[1])
                    
                    # Ensure selling_price > cost_price
                    while selling_price <= cost_price:
                        selling_price = np.random.uniform(price_range[0], price_range[1])

                    margin = selling_price - cost_price
                    
                    # Quality and performance scores correlated with price but with noise
                    base_quality = (selling_price - price_range[0]) / (price_range[1] - price_range[0]) * 100
                    quality_score = int(np.clip(base_quality + np.random.normal(0, 15), 20, 100))
                    performance_score = int(np.clip(base_quality + np.random.normal(0, 15), 20, 100))

                    # Product specs
                    ram_options = specs.get("ram", [0])
                    ram_gb = ram_options[np.random.randint(0, len(ram_options))] if isinstance(ram_options, list) and len(ram_options) > 0 else 0
                    
                    storage_options = specs.get("storage", [0])
                    storage_gb = storage_options[np.random.randint(0, len(storage_options))] if isinstance(storage_options, list) and len(storage_options) > 0 else 0
                    
                    processor_tier_options = specs.get("processor", ["N/A"])
                    processor_tier = processor_tier_options[np.random.randint(0, len(processor_tier_options))] if isinstance(processor_tier_options, list) and len(processor_tier_options) > 0 else "N/A"
                    
                    warranty_months = {
                        "Laptops": np.random.choice([12, 24, 36]),
                        "Smartphones": np.random.choice([12, 18]),
                        "Tablets": np.random.choice([12, 24]),
                        "Monitors": np.random.choice([24, 36]),
                        "Printers": np.random.choice([12, 24]),
                    }.get(category, 12)

                    products.append({
                        "product_id": product_id,
                        "product_name": f"{category[:-1]} {subcat} {brands[np.random.randint(0, len(brands))]}",
                        "category": category,
                        "subcategory": subcat,
                        "brand": brands[np.random.randint(0, len(brands))],
                        "cost_price": round(cost_price, 2),
                        "selling_price": round(selling_price, 2),
                        "margin": round(margin, 2),
                        "quality_score": quality_score,
                        "performance_score": performance_score,
                        "ram_gb": ram_gb if ram_gb > 0 else None,
                        "storage_gb": storage_gb if storage_gb > 0 else None,
                        "processor_tier": processor_tier if processor_tier != "N/A" else None,
                        "warranty_months": warranty_months,
                        "active": True,
                        "stock_quantity": np.random.randint(10, 500),
                    })
                    product_id += 1

        self.products_df = pd.DataFrame(products)
        return self.products_df

    def generate_customers(self) -> pd.DataFrame:
        """Generate customer base with tier assignment based on simulated behavior."""
        customers = []

        # Simulate customer spending behavior and assign tiers
        for customer_id in range(1, self.num_customers + 1):
            # Generate base spending behavior
            spending_behavior = np.random.exponential(scale=2.0)  # Log-normal-ish distribution
            invoice_count = max(1, int(np.random.normal(5, 2)))
            total_spend = spending_behavior * invoice_count * 20000
            avg_invoice_value = total_spend / invoice_count
            purchase_frequency = np.random.choice(["Weekly", "Bi-weekly", "Monthly", "Quarterly"])

            # Assign tier based on behavior, not randomly
            if total_spend > np.percentile([spending_behavior * i * 20000 for i in range(1, 10)], 66):
                tier = "Gold"
            elif total_spend > np.percentile([spending_behavior * i * 20000 for i in range(1, 10)], 33):
                tier = "Silver"
            else:
                tier = "Bronze"

            preferred_category = np.random.choice(list(self.cross_sell_patterns.keys()))
            preferred_brands = self.products_df[self.products_df["category"] == preferred_category]["brand"].unique()
            preferred_brand = preferred_brands[np.random.randint(0, len(preferred_brands))] if len(preferred_brands) > 0 else "Generic"

            customers.append({
                "customer_id": customer_id,
                "tier": tier,
                "total_spend": round(total_spend, 2),
                "invoice_count": invoice_count,
                "avg_invoice_value": round(avg_invoice_value, 2),
                "preferred_category": preferred_category,
                "preferred_brand": preferred_brand,
                "purchase_frequency": purchase_frequency,
            })

        self.customers_df = pd.DataFrame(customers)
        return self.customers_df

    def generate_invoices_and_items(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Generate invoices and invoice items with hidden cross-sell patterns."""
        invoices = []
        invoice_items = []
        invoice_id = 1
        
        # Base date: 12 months ago
        start_date = datetime.now() - timedelta(days=365)

        for _ in range(self.num_invoices):
            customer_id = np.random.randint(1, self.num_customers + 1)
            customer = self.customers_df[self.customers_df["customer_id"] == customer_id].iloc[0]
            
            # Random invoice date within past 12 months
            invoice_date = start_date + timedelta(days=np.random.randint(0, 365))
            
            # Determine number of products in this invoice (1-8, with bias toward 1-3)
            num_products = np.random.choice([1, 2, 3, 4, 5, 6, 7, 8], p=[0.30, 0.25, 0.20, 0.10, 0.07, 0.04, 0.02, 0.02])
            
            # Start with a primary product (often from preferred category)
            if np.random.random() < 0.6:  # 60% chance to pick from preferred category
                category_products = self.products_df[self.products_df["category"] == customer["preferred_category"]]
            else:
                category_products = self.products_df
            
            primary_product_idx = np.random.randint(0, len(category_products))
            primary_product = category_products.iloc[primary_product_idx]
            
            selected_products = [primary_product]
            selected_product_ids = {primary_product["product_id"]}
            
            # Apply cross-sell patterns
            primary_category = primary_product["category"]
            if primary_category in self.cross_sell_patterns:
                related_categories = self.cross_sell_patterns[primary_category]
                
                for related_category, base_probability in related_categories.items():
                    # Adjust probability based on customer tier
                    tier_multiplier = {"Bronze": 0.7, "Silver": 1.0, "Gold": 1.2}[customer["tier"]]
                    adjusted_prob = min(base_probability * tier_multiplier, 0.95)
                    
                    # Add some noise (5-10%)
                    noise = np.random.normal(0, 0.05)
                    final_prob = np.clip(adjusted_prob + noise, 0, 1)
                    
                    if np.random.random() < final_prob and len(selected_products) < num_products:
                        # Find product in related category
                        related_products = self.products_df[self.products_df["category"] == related_category]
                        if len(related_products) > 0:
                            related_product = related_products.iloc[np.random.randint(0, len(related_products))]
                            if related_product["product_id"] not in selected_product_ids:
                                selected_products.append(related_product)
                                selected_product_ids.add(related_product["product_id"])
            
            # Fill remaining slots with random products
            while len(selected_products) < num_products:
                random_product = self.products_df.iloc[np.random.randint(0, len(self.products_df))]
                if random_product["product_id"] not in selected_product_ids:
                    selected_products.append(random_product)
                    selected_product_ids.add(random_product["product_id"])
            
            # Calculate invoice total and create invoice
            total_amount = 0
            for product in selected_products:
                quantity = np.random.choice([1, 2, 3, 4, 5], p=[0.75, 0.12, 0.08, 0.03, 0.02])
                # B2B bulk: occasionally increase quantity
                if np.random.random() < 0.05 and product["category"] in ["Mice", "Keyboards", "Chargers"]:
                    quantity = np.random.randint(5, 20)
                
                unit_price = product["selling_price"]
                total_amount += quantity * unit_price
                
                invoice_items.append({
                    "invoice_id": invoice_id,
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "unit_price": round(unit_price, 2),
                })
            
            invoices.append({
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "invoice_date": invoice_date.strftime("%Y-%m-%d"),
                "total_amount": round(total_amount, 2),
            })
            
            invoice_id += 1

        self.invoices_df = pd.DataFrame(invoices)
        self.invoice_items_df = pd.DataFrame(invoice_items)
        
        return self.invoices_df, self.invoice_items_df

    def validate_data(self) -> Dict[str, any]:
        """Validate generated data and return validation results."""
        validation_errors = []
        
        # Check for orphan invoice items
        valid_invoice_ids = set(self.invoices_df["invoice_id"])
        orphan_items = self.invoice_items_df[~self.invoice_items_df["invoice_id"].isin(valid_invoice_ids)]
        if len(orphan_items) > 0:
            validation_errors.append(f"Found {len(orphan_items)} orphan invoice items")
        
        # Check for invalid customer references
        valid_customer_ids = set(self.customers_df["customer_id"])
        invalid_customers = self.invoices_df[~self.invoices_df["customer_id"].isin(valid_customer_ids)]
        if len(invalid_customers) > 0:
            validation_errors.append(f"Found {len(invalid_customers)} invoices with invalid customer IDs")
        
        # Check for invalid product references
        valid_product_ids = set(self.products_df["product_id"])
        invalid_products = self.invoice_items_df[~self.invoice_items_df["product_id"].isin(valid_product_ids)]
        if len(invalid_products) > 0:
            validation_errors.append(f"Found {len(invalid_products)} invoice items with invalid product IDs")
        
        # Check for negative prices/quantities
        negative_prices = self.products_df[(self.products_df["cost_price"] < 0) | (self.products_df["selling_price"] < 0)]
        if len(negative_prices) > 0:
            validation_errors.append(f"Found {len(negative_prices)} products with negative prices")
        
        negative_quantities = self.invoice_items_df[self.invoice_items_df["quantity"] < 1]
        if len(negative_quantities) > 0:
            validation_errors.append(f"Found {len(negative_quantities)} invoice items with invalid quantities")
        
        # Check cost < selling price
        invalid_margins = self.products_df[self.products_df["cost_price"] >= self.products_df["selling_price"]]
        if len(invalid_margins) > 0:
            validation_errors.append(f"Found {len(invalid_margins)} products where cost_price >= selling_price")
        
        # Validate invoice totals
        computed_totals = self.invoice_items_df.groupby("invoice_id").apply(
            lambda row: (row["quantity"] * row["unit_price"]).sum(),
            include_groups=False
        )
        invoice_totals = self.invoices_df.set_index("invoice_id")["total_amount"]
        # Round both to 2 decimals for comparison
        computed_totals = computed_totals.round(2)
        mismatched = ~computed_totals.eq(invoice_totals)
        if mismatched.any():
            validation_errors.append(f"Found {mismatched.sum()} invoices with mismatched totals")
        
        return {
            "valid": len(validation_errors) == 0,
            "errors": validation_errors,
        }

    def compute_summary(self) -> Dict:
        """Compute dataset summary statistics."""
        # Merge data for analysis
        items_with_products = self.invoice_items_df.merge(
            self.products_df[["product_id", "selling_price", "cost_price"]],
            on="product_id"
        )
        
        # Top 20 products by sales volume
        top_products = self.invoice_items_df.groupby("product_id").agg({
            "quantity": "sum",
        }).nlargest(20, "quantity").reset_index()
        
        # Add product names
        top_products = top_products.merge(
            self.products_df[["product_id", "product_name"]],
            on="product_id"
        )
        
        # Top product pairs by co-occurrence
        product_pairs = {}
        for invoice_id in self.invoice_items_df["invoice_id"].unique():
            products_in_invoice = self.invoice_items_df[self.invoice_items_df["invoice_id"] == invoice_id]["product_id"].tolist()
            for i in range(len(products_in_invoice)):
                for j in range(i + 1, len(products_in_invoice)):
                    pair = tuple(sorted([products_in_invoice[i], products_in_invoice[j]]))
                    product_pairs[pair] = product_pairs.get(pair, 0) + 1
        
        top_pairs = sorted(product_pairs.items(), key=lambda x: x[1], reverse=True)[:20]
        
        # Revenue and margin
        revenue = items_with_products["quantity"].mul(items_with_products["selling_price"]).sum()
        total_margin = items_with_products["quantity"].mul(
            items_with_products["selling_price"] - items_with_products["cost_price"]
        ).sum()
        
        summary = {
            "generated_at": datetime.now().isoformat(),
            "seed": self.seed,
            "configuration": {
                "num_customers": self.num_customers,
                "num_invoices": self.num_invoices,
            },
            "dataset_stats": {
                "num_customers": len(self.customers_df),
                "num_products": len(self.products_df),
                "num_invoices": len(self.invoices_df),
                "num_invoice_items": len(self.invoice_items_df),
                "avg_invoice_value": round(self.invoices_df["total_amount"].mean(), 2),
                "avg_products_per_invoice": round(
                    self.invoice_items_df.groupby("invoice_id").size().mean(), 2
                ),
                "total_revenue": round(revenue, 2),
                "total_margin": round(total_margin, 2),
                "margin_percent": round((total_margin / revenue) * 100, 2) if revenue > 0 else 0,
            },
            "customer_tier_distribution": {
                "Bronze": int(len(self.customers_df[self.customers_df["tier"] == "Bronze"])),
                "Silver": int(len(self.customers_df[self.customers_df["tier"] == "Silver"])),
                "Gold": int(len(self.customers_df[self.customers_df["tier"] == "Gold"])),
            },
            "top_20_products": top_products[["product_id", "product_name", "quantity"]].to_dict("records"),
            "top_product_pairs": [
                {
                    "product_pair": pair[0],
                    "co_occurrences": pair[1],
                }
                for pair in top_pairs
            ],
            "validation": self.validate_data(),
        }
        
        return summary

    def save_data(self, output_dir: str = "data"):
        """Save generated data to CSV files."""
        os.makedirs(output_dir, exist_ok=True)
        
        self.products_df.to_csv(f"{output_dir}/products.csv", index=False)
        self.customers_df.to_csv(f"{output_dir}/customers.csv", index=False)
        self.invoices_df.to_csv(f"{output_dir}/invoices.csv", index=False)
        self.invoice_items_df.to_csv(f"{output_dir}/invoice_items.csv", index=False)
        
        summary = self.compute_summary()
        with open(f"{output_dir}/dataset_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        return summary

    def print_summary(self, summary: Dict):
        """Print summary statistics."""
        print("\n" + "="*60)
        print("SYNTHETIC DATASET GENERATION COMPLETE")
        print("="*60)
        
        print("\nDATASET STATISTICS:")
        print(f"  Customers: {summary['dataset_stats']['num_customers']}")
        print(f"  Products: {summary['dataset_stats']['num_products']}")
        print(f"  Invoices: {summary['dataset_stats']['num_invoices']}")
        print(f"  Invoice Items: {summary['dataset_stats']['num_invoice_items']}")
        print(f"  Avg Invoice Value: ₹{summary['dataset_stats']['avg_invoice_value']:,.2f}")
        print(f"  Avg Products per Invoice: {summary['dataset_stats']['avg_products_per_invoice']}")
        print(f"  Total Revenue: ₹{summary['dataset_stats']['total_revenue']:,.2f}")
        print(f"  Total Margin: ₹{summary['dataset_stats']['total_margin']:,.2f}")
        print(f"  Margin %: {summary['dataset_stats']['margin_percent']}%")
        
        print("\nCUSTOMER TIER DISTRIBUTION:")
        for tier, count in summary['customer_tier_distribution'].items():
            pct = (count / summary['dataset_stats']['num_customers']) * 100
            print(f"  {tier}: {count} ({pct:.1f}%)")
        
        print("\nTOP 20 PRODUCTS BY SALES VOLUME:")
        for i, product in enumerate(summary['top_20_products'][:10], 1):
            print(f"  {i}. {product['product_name']} - {product['quantity']} units")
        
        print("\nTOP 10 PRODUCT PAIRS (Co-occurrence):")
        for i, pair in enumerate(summary['top_product_pairs'][:10], 1):
            product_ids = pair['product_pair']
            product_names = self.products_df[self.products_df['product_id'].isin(product_ids)]['product_name'].tolist()
            print(f"  {i}. {product_names[0]} + {product_names[1]} - {pair['co_occurrences']} times")
        
        print("\nVALIDATION:")
        if summary['validation']['valid']:
            print("  ✓ All validation checks passed")
        else:
            print("  ✗ Validation errors found:")
            for error in summary['validation']['errors']:
                print(f"    - {error}")
        
        print("\nDATA SAVED TO: data/")
        print("  - products.csv")
        print("  - customers.csv")
        print("  - invoices.csv")
        print("  - invoice_items.csv")
        print("  - dataset_summary.json")
        print("\n" + "="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic B2B electronics invoicing data for cross-sell/upsell recommendation engine"
    )
    parser.add_argument("--customers", type=int, default=10000, help="Number of customers to generate (default: 10000)")
    parser.add_argument("--invoices", type=int, default=50000, help="Number of invoices to generate (default: 50000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--output", type=str, default="data", help="Output directory (default: data)")
    
    args = parser.parse_args()
    
    print(f"Generating synthetic data with seed={args.seed}...")
    print(f"  Customers: {args.customers}")
    print(f"  Invoices: {args.invoices}")
    
    generator = ElectronicsDataGenerator(
        num_customers=args.customers,
        num_invoices=args.invoices,
        seed=args.seed
    )
    
    print("\n1. Generating products...")
    generator.generate_products()
    
    print("2. Generating customers...")
    generator.generate_customers()
    
    print("3. Generating invoices and items with cross-sell patterns...")
    generator.generate_invoices_and_items()
    
    print("4. Computing summary and validation...")
    summary = generator.save_data(args.output)
    
    generator.print_summary(summary)


if __name__ == "__main__":
    main()