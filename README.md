# lis-ask
Enhanced_sql_agent.py is the main orchestrator and hits the DB with SQL created
app_client.py is the app script, built using Streamlit frontend
extract_schema.py is built for extracting the schema from the database, along with the indices
llm_sql_generator.py is for sending prompts to the LLM for generating the SQL Expression with all the rules and logics
nl_response_generator.py is for generating natural language responses for the data received after running the SQL Expression
placeholder_resolver.py is for resolving the placeholders in SQL for the parameters(date range, stores' names, users' details, ect) extracted from the user query
sql_validator.py validates the query to check that only the 'Select' expression is passed on to hit the DB
requirements.txt has all the Python dependencies that were needed for building this project
