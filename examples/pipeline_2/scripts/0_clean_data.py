import pandas as pd


def check_variables(df, expected_variables):
    missing = []
    for i in expected_variables:
        if i in df.columns:
            pass
        else:
            missing.append(i)
    if missing == []:
        print("All variables present")
    print(f"Missing the following variables: {missing}")


def remove_identifiable(df,identifiable_cols):
    for i in identifiable_cols:
        if i in df.columns:
            df = df.drop(i, axis = 1)
        else:
            pass
    return df


def standardise_columns(df):
    df.columns = [col.lower() for col in df.columns]
    df.columns = [col.capitalize() for col in df.columns]
    for item in df.columns:
        df[item] = df[item].apply(lambda x: x.lower() if isinstance(x,str) else x)
        df[item] = df[item].apply(lambda x: x.strip() if isinstance(x,str) else x)
    return df



def main():
    orders = pd.read_csv("examples/pipeline_2/data/orders.csv")

    expected_variables = ["order_id",
                      "customer_name",
                      "region",
                      "product",
                      "quantity",
                      "unit_price",
                      "order_date",
                      "order_method"]

    identifiable_cols = ["customer_name",
                         "age",
                         "dob",
                         "address"]
    
    check_variables(orders,expected_variables)
    print(orders.dtypes)
    orders = remove_identifiable(orders, identifiable_cols)
    orders = standardise_columns(orders)
    orders.to_csv("examples/pipeline_2/data/orders_cleaned.csv", index = False)

main()