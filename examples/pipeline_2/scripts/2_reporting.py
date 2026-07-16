import pandas as pd
import tabulate
from pathlib import Path

orders = pd.read_csv("examples/pipeline_2/processed_data/orders_prepped.csv")

report = []

num_format = "{:.2f}"
##PROFIT PER REGION##
profit_per_region = orders.groupby("Region")["Order_profit"].sum()

highest_prof_region = profit_per_region.idxmax().capitalize()
highest_prof_value = num_format.format((profit_per_region.max()))

lowest_prof_region = profit_per_region.idxmin().capitalize()
lowest_prof_region = num_format.format((profit_per_region.min()))

##QUANTITY PER REGION##
quantity_per_region = orders.groupby("Region")["Quantity"].sum()

highest_quant_region = quantity_per_region.idxmax().capitalize()
highest_quant_value = quantity_per_region.max()

lowest_quant_region = quantity_per_region.idxmin().capitalize()
lowest_quant_value = quantity_per_region.min()

##ORDER DAY POP##
delivery_day_frequency = orders["Order_day"].value_counts()
highest_delivery_day = delivery_day_frequency.idxmin().capitalize()

##ORDER COUNTS##
large_order_num = (orders["Large_order"] == True).sum()

small_order_num = (orders["Small_order"] == True).sum()

##ORDERS PER REGION##
orders_per_region = orders["Region"].value_counts()
highest_order_region = quantity_per_region.idxmax().capitalize()

##TOTALS##
total_count = orders.count()
total_profit = num_format.format(orders["Order_profit"].sum())

##PROFIT PER PRODUCT##
profit_per_product = orders.groupby("Product")["Order_profit"].sum().sort_values(ascending=False)

highest_profit_product = profit_per_product.idxmax().capitalize()
highest_profit_value = num_format.format((profit_per_product.max()))

lowest_profit_product = profit_per_product.idxmin().capitalize()
lowest_profit_value = num_format.format((profit_per_product.min()))

##CURATE REPORT##
report.append("# June 2026 Order Summary")
report.append("")
report.append("## Summary")
report.append("")
report.append(f"Total Orders: {total_count}")
report.append("")
report.append(f"Total Profit: {total_profit}")
report.append("")
report.append("## Region Analysis")
report.append(f"The region that produced the highest number of orders: {highest_order_region}")
report.append(f"The region that produced the highest profit: {highest_prof_region} at £{highest_prof_value}")
report.append(f"The region that produced the lowest profit: {lowest_prof_region} at £{lowest_profit_value}")
report.append(f"The region that had the highest quantity of items ordered: {highest_quant_region} at {highest_quant_value}")
report.append(f"The region that had the highest quantity of items ordered: {lowest_quant_region} at {lowest_quant_value}")
report.append("")
report.append("## Product Analysis")
report.append(f"The product that had the highest profit: {highest_profit_product} at £{highest_profit_value}")
report.append(f"The product that had the lowest profit: {lowest_profit_product} at £{lowest_profit_value}")
report.append("")
report.append("## Order Analysis")
report.append(f"The most orders occured on a {highest_delivery_day}.")
report.append(f"{large_order_num} order/s were Large (greater than 75% of the rest).")
report.append(f"{small_order_num} order/s were Small (less than 25% of the rest).")

output_path = Path("")