import pandas as pd
import numpy as np
from datetime import timedelta

def correct_date_time(df):
    df["Order_date"] = pd.to_datetime(df["Order_date"])
    return df


def estimate_delivery(df, delivery_times):
    df["Estimated_delvery_date"] = df["Order_date"] + pd.to_timedelta(df["Region"].map(delivery_times), unit = "D")
    df["Delivery_day"] = df["Estimated_delvery_date"].dt.day_name()
    return df 

def total_cost(df):
    df["Total_cost"] = df["Quantity"] * df["Unit_price"]
    return df

def order_date_values(df):
    df["Order_day"] = df["Order_date"].dt.day_name()
    df["Order_month"] = df["Order_date"].dt.month_name()
    return(df)

def size_order_alert(df):
    df["Large_order"] = df["Quantity"] > df["Quantity"].quantile(0.75)
    df["Small_order"] = df["Quantity"] < df["Quantity"].quantile(0.25)
    return df

def postage_cost(df):
    df["Postage"] = np.select(
        [
            df["Large_order"],
            df["Small_order"]
        ],
        [
            5.00,
            1.00
        ],
        default = 2.50
    )
    return df

def production_cost(df):
    df["Total_production_cost"] = np.select(
        [
            df["Product"] == "notebook",
            df["Product"] == "pen",
            df["Product"] == "folder"
        ],
        [
            (1.00*df["Quantity"]),
            (0.3*df["Quantity"]),
            (0.75*df["Quantity"])

        ],
        default = 0
    )
    return df

def profit_per_order(df):
    df["Order_profit"] = df["Total_cost"]-df["Total_production_cost"]-df["Postage"]
    return df




def main(context=None):
    config = context.get_stage_config("1_derive_vars")
    
    df = pd.read_csv(config["input_location"])
    delivery_times = config["delivery_times"]

    df = correct_date_time(df)
    df = estimate_delivery(df, delivery_times)
    df = total_cost(df)
    df = order_date_values(df)
    df = size_order_alert(df)
    df = postage_cost(df)
    df = production_cost(df)
    df = profit_per_order(df)
    df.to_csv(config["output_location"], index = False)



if __name__ == "__main__":
    main()