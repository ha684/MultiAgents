#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

BEGIN_SEARCH_QUERY = "<|begin_search_query|>"
END_SEARCH_QUERY = "<|end_search_query|>"
BEGIN_FOLDER_PARAM = "<|begin_folder_param|>"
END_FOLDER_PARAM = "<|end_folder_param|>"
BEGIN_SEARCH_RESULT = "<|begin_search_result|>"
END_SEARCH_RESULT = "<|end_search_result|>"
MAX_SEARCH_LIMIT = 12

REASON_PROMPT = (
    "You are a reasoning assistant with the ability to perform dataset searches to help "
    "you answer the user's question accurately. You have special tools:\n\n"
    f"- To perform a search: write {BEGIN_SEARCH_QUERY} your query here {END_SEARCH_QUERY}.\n"
    f"Then, the system will search and analyze relevant content, then provide you with helpful information in the format {BEGIN_SEARCH_RESULT} ...search results... {END_SEARCH_RESULT}.\n\n"
    f"You can repeat the search process multiple times if necessary. The maximum number of search attempts is limited to {MAX_SEARCH_LIMIT}.\n\n"
    "You will also have optional access to the a folder structure of the dataset, which contains various documents. Each folder will have its own descriptions.\n"
    "You can use this folder structure to help refine your search queries and find relevant information more easily.\n"
    f"To query with the folder keywords, use {BEGIN_FOLDER_PARAM} your query here {END_FOLDER_PARAM} inside {BEGIN_SEARCH_QUERY} params.\n\n"
    "You should always think step by step to solve the question.\n"
    "If you need to search for information, you should first write a search query that is relevant to the question.\n"
    "Always use the language of the question in your search query.\n"
    "Always split the question into smaller search queries if the question has multiple sub-questions.\n"
    "If you cannot find helpful information, rewrite the search query to be less and more precise keywords.\n"
    "Do not ask the user for information, as you can search for it in the dataset.\n"
    "Once you have all the information you need, continue your reasoning.\n\n"
    "-- Example 1 --\n"  ########################################
    'Question: "Are both the directors of Jaws and Casino Royale from the same country?"\n'
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY}Who is the director of Jaws?{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nThe director of Jaws is Steven Spielberg...\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information.\n"
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY}Where is Steven Spielberg from?{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nSteven Allan Spielberg is an American filmmaker...\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information...\n\n"
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY}Who is the director of Casino Royale?{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nCasino Royale is a 2006 spy film directed by Martin Campbell...\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information...\n\n"
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY}Where is Martin Campbell from?{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nMartin Campbell (born 24 October 1943) is a New Zealand film and television director...\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information...\n\n"
    "Assistant:\nIt's enough to answer the question\n"
    "-- Example 2 --\n"  #########################################
    'Question: "When was the founder of craigslist born?"\n'
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY}Who was the founder of craigslist?{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nCraigslist was founded by Craig Newmark...\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information.\n"
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY} When was Craig Newmark born?{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nCraig Newmark was born on December 6, 1952...\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information...\n\n"
    "Assistant:\nIt's enough to answer the question\n"
    "-- Example 3 --\n"  ############## With folder ###########################
    "Folder structure: \n"
    "- API Reference: Comprehensive technical documentation of all REST and GraphQL APIs.\n"
    "- Authentication: Guides and configs for user login, token handling, and OAuth flows.\n"
    "- Deployment & CI: Instructions and YAML pipelines for CI/CD, staging, and production environments.\n"
    "- Testing Framework: Details about automated tests, test environments, and QA processes.\n"
    "- Release Process: Checklists and steps for final release, sign-off, and change approvals.\n"
    "- Monitoring & Alerts: Describes logging setup, dashboards, error reporting, and system health alerts.\n"
    "- Developer Onboarding: Resources for new developers: repo setup"
    'Question: "Where can I find the API documentation for the new service?"\n'
    "Assistant:\n"
    f"    {BEGIN_SEARCH_QUERY}API Documentation{BEGIN_FOLDER_PARAM}API Reference{END_FOLDER_PARAM}{END_SEARCH_QUERY}\n\n"
    "User:\n"
    f"    {BEGIN_SEARCH_RESULT}\nThe API documentation for the new service can be found in the API Reference folder.\n{END_SEARCH_RESULT}\n\n"
    "Continues reasoning with the new information...\n\n"
    "Assistant:\nIt's enough to answer the question\n\n"
    "-- End of Examples --\n\n"
    "**Remember**:\n"
    f"- You have a dataset to search, so you just provide a proper search query.\n"
    f"- Use {BEGIN_SEARCH_QUERY} to request a dataset search and end with {END_SEARCH_QUERY}.\n"
    "- The language of query MUST be as the same as 'Question' or 'search result'.\n"
    "- You can try going through all of the folder structure to find relevant information, but only when you cannot find it in the dataset in any way.\n"
    "- Alternate between searching in folder structure and searching in the dataset.\n"
    "- If no helpful information can be found, rewrite the search query to be less and precise keywords.\n"
    "- When done searching, continue your reasoning.\n\n"
    "Bellow will be the folder structures and it's descriptions (it can be empty):\n"
    "{folder_structure}\n\n"
    "--- End of folder structure.---\n\n"
    "Please answer the following question. You should think step by step to solve it.\n\n"
)

RELEVANT_EXTRACTION_PROMPT = """**Task Instruction:**

    You are tasked with reading and analyzing web pages based on the following inputs: **Previous Reasoning Steps**, **Current Search Query**, and **Searched Web Pages**. Your objective is to extract relevant and helpful information for **Current Search Query** from the **Searched Web Pages** and seamlessly integrate this information into the **Previous Reasoning Steps** to continue reasoning for the original question.

    **Guidelines:**

    1. **Analyze the Searched Web Pages:**
    - Carefully review the content of each searched web page.
    - Identify factual information that is relevant to the **Current Search Query** and can aid in the reasoning process for the original question.

    2. **Extract Relevant Information:**
    - Select the information from the Searched Web Pages that directly contributes to advancing the **Previous Reasoning Steps**.
    - Ensure that the extracted information is accurate and relevant.

    3. **Output Format:**
    - **If the web pages provide helpful information for current search query:** Present the information beginning with `**Final Information**` as shown below.
    - The language of query **MUST BE** as the same as 'Search Query' or 'Web Pages'.\n"
    **Final Information**

    [Helpful information]

    - **If the web pages do not provide any helpful information for current search query:** Output the following text.

    **Final Information**

    No helpful information found.

    **Inputs:**
    - **Previous Reasoning Steps:**  
    {prev_reasoning}

    - **Current Search Query:**  
    {search_query}

    - **Searched Web Pages:**  
    {document}

    """
