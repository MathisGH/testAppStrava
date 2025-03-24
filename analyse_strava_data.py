import pandas as pd
import os

folder = "Data"
df = pd.concat([pd.read_csv(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".csv")], ignore_index=True) # Concat toutes les data dans un seul df

print(df.head())
print(df.columns)