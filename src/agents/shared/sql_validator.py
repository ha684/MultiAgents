# src/agents/shared/sql_validator.py
"""
SQL Validator - Ensures only safe SELECT queries are executed
"""

import re
from typing import Any

import sqlparse
from sqlparse.sql import Identifier, IdentifierList
from sqlparse.tokens import DML

from src.utils.logger_conf import logger


class SqlValidator:
    """
    Validates SQL queries to ensure they are safe (SELECT-only) and prevents
    any data modification operations.
    """

    FORBIDDEN_KEYWORDS = {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "REPLACE",
        "MERGE",
        "GRANT",
        "REVOKE",
        "EXEC",
        "EXECUTE",
        "CALL",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
    }

    FORBIDDEN_PATTERNS = [
        r";\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE)",
        r"--",
        r"/\*.*?\*/",
        r"\bINTO\s+OUTFILE\b",
        r"\bLOAD\s+DATA\b",
        r"\bSELECT\s+.*\bINTO\s+",
    ]

    @staticmethod
    def validate_query(sql_query: str) -> dict[str, Any]:
        """
        Validates a SQL query to ensure it's safe for execution.

        Args:
            sql_query: The SQL query to validate

        Returns:
            Dict containing:
                - is_valid: bool
                - is_select_only: bool
                - issues: List[str]
                - sanitized_query: str (if valid)
        """
        result = {
            "is_valid": False,
            "is_select_only": False,
            "issues": [],
            "sanitized_query": "",
        }

        if not sql_query or not sql_query.strip():
            result["issues"].append("Empty query provided")
            return result

        cleaned_query = sql_query.strip()

        for pattern in SqlValidator.FORBIDDEN_PATTERNS:
            if re.search(pattern, cleaned_query, re.IGNORECASE | re.DOTALL):
                result["issues"].append(f"Forbidden pattern detected: {pattern}")
                logger.warning(
                    f"SQL validation failed: Forbidden pattern {pattern} in query"
                )
                return result

        try:
            parsed = sqlparse.parse(cleaned_query)
        except Exception as e:
            result["issues"].append(f"Failed to parse SQL: {str(e)}")
            logger.error(f"SQL parsing error: {e}")
            return result

        if not parsed:
            result["issues"].append("No valid SQL statement found")
            return result

        for statement in parsed:
            stmt_type = statement.get_type()

            if stmt_type != "SELECT":
                result["issues"].append(f"Non-SELECT statement detected: {stmt_type}")
                logger.warning(
                    f"SQL validation failed: Non-SELECT statement type {stmt_type}"
                )
                return result

            for token in statement.tokens:
                if token.ttype is DML:
                    token_value = token.value.upper()
                    if token_value in SqlValidator.FORBIDDEN_KEYWORDS:
                        result["issues"].append(
                            f"Forbidden keyword detected: {token_value}"
                        )
                        logger.warning(
                            f"SQL validation failed: Forbidden keyword {token_value}"
                        )
                        return result

                if hasattr(token, "value"):
                    token_upper = token.value.upper()
                    for forbidden in SqlValidator.FORBIDDEN_KEYWORDS:
                        if re.search(r"\b" + forbidden + r"\b", token_upper):
                            result["issues"].append(
                                f"Forbidden operation detected: {forbidden}"
                            )
                            logger.warning(
                                f"SQL validation failed: Forbidden operation {forbidden}"
                            )
                            return result

        if len(parsed) > 1:
            result["issues"].append(
                "Multiple SQL statements detected. Only single SELECT allowed."
            )
            logger.warning("SQL validation failed: Multiple statements")
            return result

        formatted_query = sqlparse.format(
            cleaned_query,
            reindent=True,
            keyword_case="upper",
            strip_comments=True,
        )

        if not formatted_query.strip().upper().startswith("SELECT"):
            result["issues"].append("Query must start with SELECT")
            logger.warning("SQL validation failed: Query does not start with SELECT")
            return result

        result["is_valid"] = True
        result["is_select_only"] = True
        result["sanitized_query"] = formatted_query

        logger.info("SQL query validated successfully")
        return result

    @staticmethod
    def extract_table_names(sql_query: str) -> list[str]:
        """
        Extracts table names from a SQL query.

        Args:
            sql_query: The SQL query

        Returns:
            List of table names found in the query
        """
        table_names = []

        try:
            parsed = sqlparse.parse(sql_query)
            for statement in parsed:
                for token in statement.tokens:
                    if isinstance(token, IdentifierList):
                        for identifier in token.get_identifiers():
                            table_names.append(str(identifier))
                    elif isinstance(token, Identifier):
                        table_names.append(str(token))

        except Exception as e:
            logger.error(f"Error extracting table names: {e}")

        return table_names

    @staticmethod
    def validate_and_sanitize(sql_query: str) -> dict[str, Any]:
        """
        Convenience method that validates and returns sanitized query.

        Args:
            sql_query: The SQL query to validate

        Returns:
            Validation result dictionary
        """
        return SqlValidator.validate_query(sql_query)
