import pandas as pd
import duckdb

p = "data/adjusted_daily/SHIVAUM.parquet"
df = pd.read_parquet(p)
print("SHIVAUM dates:", df['date'].min(), "to", df['date'].max(), "len:", len(df))

# Check when SHIVAUM traded
print(df.tail(20))
