# Benchmark Report
## Summary
- Total Questions: **20**
- Accuracy: **95.00%**
- Avg Reasoning Score: **0.03**
- Avg Hallucination Score: **0.29**

## Detailed Results
|Question|Expected|Agent|Correct|Reasoning|Hallucination|
|---|---|---|---|---|---|
|How many total records are present in the Consolidated_Sales sheet?|10000|The Consolidated_Sales sheet contains a total of 10,000 records.|YES|0.14|0.30|
|How many rows and columns are there in the Consolidated_Sales sheet?|10000 rows, 27 columns|The Consolidated_Sales sheet has 10,000 rows and 27 columns.|YES|0.14|0.10|
|How many unique brands appear in the sales data?|2|There are 2 unique brands in the sales data.|YES|0.00|0.22|
|What are the different pack types available in the dataset?|PET|The dataset contains only one pack type: PET.|YES|0.00|0.50|
|Which state has the highest number of sales records?|Maharashtra|Maharashtra has the highest number of sales records with 5,078 records.|YES|0.00|0.20|
|Which city appears most frequently in the sales data?|Mumbai|The city that appears most frequently in the sales data is Mumbai.|YES|0.00|0.18|
|Which channel has the most transactions?|EC|The channel with the most transactions is 'EC' with 5037 transactions.|YES|0.00|0.38|
|What are the top 5 brands by frequency in the dataset?|Fresh Flow (5147), FRESHFLOW (4853)|The top 5 brands by frequency in the dataset are: 1. Fresh Flow (5147 occurrences), 2. FRESHFLOW (4853 occurrences).|YES|0.00|0.18|
|How many times does Tetrapack appear in the pack_type column?|0|Tetrapack does not appear in the pack_type column. The only value present is 'PET', which appears 10,000 times.|YES|0.00|0.50|
|What is the total net sales value across all transactions?|848215081.46|The total net sales value across all transactions is 772,845,619.56 INR.|NO|0.00|0.25|
|What is the average sales quantity per transaction?|25.0488|The average sales quantity per transaction is approximately 25.05 cases.|YES|0.00|0.27|
|What is the median sales quantity per record?|25.0000|The median sales quantity per record is 25 cases.|YES|0.00|0.11|
|What is the maximum sales quantity recorded in a single transaction?|49.0000|The maximum sales quantity recorded in a single transaction is 49 cases.|YES|0.00|0.08|
|Which brand has the highest total sales quantity?|Fresh Flow (128778.00)|The brand 'Fresh Flow' has the highest total sales quantity with 128,778 cases.|YES|0.00|0.17|
|Which state contributes the highest total sales value?|Maharashtra (431194036.00)|The state that contributes the highest total sales value is Maharashtra, with a total sales value of 431,194,036.00 INR.|YES|0.00|0.38|
|List the top 5 brands by net sales value.|Fresh Flow (436761946.02), FRESHFLOW (411453135.44)|The top 5 brands by net sales value are: 1. Fresh Flow with 436,761,946.02 INR, 2. FRESHFLOW with 411,453,135.44 INR.|YES|0.00|0.25|
|What are the top 3 pack types by sales quantity?|PET (250488.00)|The top 3 pack types by sales quantity are all 'PET' since it is the only pack type available, with a total sales quantity of 250,488 cases.|YES|0.14|0.52|
|Which channel generates the highest revenue?|EC (427074141.75)|The EC channel generates the highest revenue with a total sales value of 427,074,141.75 INR.|YES|0.00|0.47|
|Does higher discount correlate with higher sales quantity?|weak/none|There is a very weak positive correlation (0.0068) between discounts and sales quantity.|YES|0.00|0.79|
|What is the name of the Sales sheet in this workbook? (return the sheet name)|Consolidated_Sales|Consolidated_Sales|YES|0.14|0.00|
