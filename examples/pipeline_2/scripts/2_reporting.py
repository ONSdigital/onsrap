import pandas as pd
from pathlib import Path

##PROFIT PER REGION##
def per_region_profits(orders, values, num_format):
    profit_per_region = orders.groupby("Region")["Order_profit"].sum()

    values["highest_prof_region"] = profit_per_region.idxmax().capitalize()
    values["highest_prof_value"] = num_format.format((profit_per_region.max()))

    values["lowest_prof_region"] = profit_per_region.idxmin().capitalize()
    values["lowest_profit_value"] = num_format.format((profit_per_region.min()))

##QUANTITY PER REGION##
def per_region_quantity(orders, values):
    quantity_per_region = orders.groupby("Region")["Quantity"].sum()

    values["highest_quant_region"] = quantity_per_region.idxmax().capitalize()
    values["highest_quant_value"] = quantity_per_region.max()

    values["lowest_quant_region"] = quantity_per_region.idxmin().capitalize()
    values["lowest_quant_value"] = quantity_per_region.min()

##ORDER DAY POP##
def orders_per_day(orders, values):
    delivery_day_frequency = orders["Order_day"].value_counts()
    values["highest_delivery_day"] = delivery_day_frequency.idxmin().capitalize()

##ORDER COUNTS##
def order_quantity(orders, values):
    values["large_order_num"] = (orders["Large_order"] == True).sum()

    values["small_order_num"] = (orders["Small_order"] == True).sum()

##ORDERS PER REGION##
def per_region_orders(orders, values):
    orders_per_region = orders["Region"].value_counts()
    values["highest_order_region"] = orders_per_region.idxmax().capitalize()

##TOTALS##
def total_summaries(orders,values,num_format):
    values["total_count"] = orders["Order_id"].count()
    values["total_profit"] = num_format.format(orders["Order_profit"].sum())

##PROFIT PER PRODUCT##
def profit_per_product(orders,values, num_format):
    df = orders.groupby("Product")["Order_profit"].sum().sort_values(ascending=False)

    values["highest_profit_product"] = df.idxmax().capitalize()
    values["highest_profit_value"] = num_format.format((df.max()))

    values["lowest_profit_product"] = df.idxmin().capitalize()
    values["lowest_profit_value"] = num_format.format((df.min()))

##CURATE REPORT##
def curate_report(report, values):
    report.append("# Order Summary")
    report.append("")
    report.append("This is an automatically generated report showing key information on orders of products.")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"Total Orders: **{values["total_count"]}**")
    report.append("")
    report.append(f"Total Profit: **£{values["total_profit"]}**")
    report.append("")
    report.append("## Region Analysis")
    report.append(f"Highest number of orders: **{values["highest_order_region"]}**")
    report.append("")
    report.append(f"Highest profit: **{values["highest_prof_region"]}** at **£{values["highest_prof_value"]}**")
    report.append("")
    report.append(f"Lowest profit: **{values["lowest_prof_region"]}** at **£{values["lowest_profit_value"]}**")
    report.append("")
    report.append(f"Highest quantity of items ordered: **{values["highest_quant_region"]}** at **{values["highest_quant_value"]}**")
    report.append("")
    report.append(f"Lowest quantity of items ordered: **{values["lowest_quant_region"]}** at **{values["lowest_quant_value"]}**")
    report.append("")
    report.append("## Product Analysis")
    report.append(f"Highest profit: **{values["highest_profit_product"]}** at **£{values["highest_profit_value"]}**")
    report.append("")
    report.append(f"Lowest profit: **{values["lowest_profit_product"]}** at **£{values["lowest_profit_value"]}**")
    report.append("")
    report.append("## Order Analysis")
    report.append("")
    report.append(f"The most orders occured on a **{values["highest_delivery_day"]}**.")
    report.append("")
    report.append(f"**{values["large_order_num"]}** order/s were Large (greater than 75% of orders for the period).")
    report.append("")
    report.append(f"**{values["small_order_num"]}** order/s were Small (less than 25% of orders for the period).")

def write_report(report):
    report_file = Path("examples/pipeline_2/outputs/order_analysis.md")

    report_file.write_text(
        "\n".join(report),
        encoding="utf-8"
    )

def main():
    orders = pd.read_csv("examples/pipeline_2/data/orders_prepped.csv")

    report = []
    values = {}

    num_format = "{:.2f}"

    per_region_profits(orders, values, num_format)
    per_region_quantity(orders, values)
    orders_per_day(orders, values)
    order_quantity(orders, values)
    per_region_orders(orders, values)
    total_summaries(orders,values,num_format)
    profit_per_product(orders,values, num_format)
    curate_report(report, values)
    write_report(report)

if __name__ == "__main__":
    main()