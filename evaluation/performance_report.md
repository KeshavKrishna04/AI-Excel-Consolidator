## Section 1 — System Overview
- The system uses **FastAPI** for HTTP endpoints and **LangGraph** to orchestrate a multi-step Q&A workflow.
- The benchmark calls the existing compiled LangGraph Q&A workflow directly (Python import), without changing the API.

## Section 2 — Pipeline Visualization
- Pipeline PNG: `evaluation/langgraph_pipeline.png`

## Section 3 — Benchmark Setup
- Dataset used: workbook used by the benchmark run
- Number of questions: **20**

## Section 4 — Results Table
| Question | Expected Answer | Agent Answer | Response Time (s) | Correct |
|---|---|---|---:|:---:|
| How many total records are present in the Consolidated_Sales sheet? | 10000 | There are 10,000 total records in the Consolidated_Sales sheet. | 47.8366 | ✅ |
| How many rows and columns are there in the Consolidated_Sales sheet? | 10000 rows, 27 columns | The Consolidated_Sales sheet has 10,000 rows and 27 columns. | 34.1503 | ✅ |
| How many unique brands appear in the sales data? | 2 | There are 2 unique brands in the sales data. | 31.5394 | ✅ |
| What are the different pack types available in the dataset? | PET | The only pack type available in the dataset is 'PET'. | 29.1772 | ✅ |
| Which state has the highest number of sales records? | Maharashtra | Maharashtra has the highest number of sales records. | 30.2142 | ✅ |
| Which city appears most frequently in the sales data? | Mumbai | The city that appears most frequently in the sales data is Mumbai. | 31.5429 | ✅ |
| Which channel has the most transactions? | EC | The channel with the most transactions is 'EC' with 5037 transactions. | 31.7055 | ✅ |
| What are the top 5 brands by frequency in the dataset? | Fresh Flow (5147), FRESHFLOW (4853) | The top 5 brands by frequency in the dataset are: 1. Fresh Flow (5147 occurrences), 2. FRESHFLOW (4853 occurrences), 3. Brand_1 (237 occurrences), 4. Brand_34 (233 occurrences), 5. Brand_32 (230 occurrences). | 32.8021 | ✅ |
| How many times does Tetrapack appear in the pack_type column? | 0 | Tetrapack does not appear in the pack_type column. | 29.7183 | ❌ |
| What is the total net sales value across all transactions? | 848215081.46 | The total net sales value across all transactions is 772,845,619.56 INR. | 35.9296 | ❌ |
| What is the average sales quantity per transaction? | 25.0488 | The average sales quantity per transaction is approximately 25.05 cases. | 30.1475 | ✅ |
| What is the median sales quantity per record? | 25.0000 | The median sales quantity per record is 25 cases. | 30.6682 | ✅ |
| What is the maximum sales quantity recorded in a single transaction? | 49.0000 | The maximum sales quantity recorded in a single transaction is 49 cases. | 33.3911 | ✅ |
| Which brand has the highest total sales quantity? | Fresh Flow (128778.00) | The brand 'Fresh Flow' has the highest total sales quantity with 128,778 cases. | 28.3312 | ✅ |
| Which state contributes the highest total sales value? | Maharashtra (431194036.00) | The state that contributes the highest total sales value is Maharashtra with a total sales value of 431,194,036.00 INR. | 28.2260 | ✅ |
| List the top 5 brands by net sales value. | Fresh Flow (436761946.02), FRESHFLOW (411453135.44) | The top 5 brands by net sales value are: 1. Fresh Flow with a net sales value of 436,761,946.02 INR, and 2. FRESHFLOW with a net sales value of 411,453,135.44 INR. | 27.5046 | ✅ |
| What are the top 3 pack types by sales quantity? | PET (250488.00) | The top 3 pack types by sales quantity are all 'PET' since it is the only pack type available, with a total sales quantity of 250,488 cases. | 27.1453 | ✅ |
| Which channel generates the highest revenue? | EC (427074141.75) | The EC channel generates the highest revenue with a total gross sales value of 427,074,141.75 INR. | 26.4172 | ✅ |
| Does higher discount correlate with higher sales quantity? | weak/none | There is a very weak positive correlation between higher discounts and higher sales quantity, with a correlation coefficient of 0.0068. | 42.5704 | ❌ |
| What is the name of the Sales sheet in this workbook? (return the sheet name) | Consolidated_Sales | Consolidated_Sales | 31.0483 | ✅ |

## Section 5 — Summary Metrics
- Total questions: **20**
- Correct answers: **17**
- Accuracy percentage: **85.00%**
- Average response time: **32.003s**

## Section 6 — Observed Bottlenecks
- If response times increase with larger datasets, likely bottlenecks are:
  - Workbook parsing time (pandas reading multiple sheets)
  - LLM latency (network + model compute)
  - Larger prompts due to higher cardinality columns
