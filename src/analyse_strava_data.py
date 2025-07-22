import pandas as pd
import os

folder = "data"
df = pd.concat([pd.read_csv(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".csv")], ignore_index=True) # Concat everything data in a single df


### WORK IN PROGRESS ###