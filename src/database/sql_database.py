"""Async SQLAlchemy wrapper around a PostgreSQL database."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Union

from sqlalchemy import (
    MetaData,
    Table,
    select,
    text,
)
from sqlalchemy.engine import URL, Result
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.expression import Executable
from sqlalchemy.types import NullType
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from src.db.repository.database_session import DatabaseSession
from src.utils.logger_conf import logger


def _format_index(index: dict) -> str:
    return (
        f"Name: {index['name']}, Unique: {index['unique']},"
        f" Columns: {str(index['column_names'])}"
    )


def truncate_word(content: Any, *, length: int, suffix: str = "...") -> str:
    """Truncate a string to a certain number of words, based on the max string length."""
    if not isinstance(content, str) or length <= 0:
        return content

    if len(content) <= length:
        return content

    return content[: length - len(suffix)].rsplit(" ", 1)[0] + suffix


def sanitize_schema(schema: str) -> str:
    """Sanitize a schema name to only contain letters, digits, and underscores."""
    if not re.match(r"^[a-zA-Z0-9_]+$", schema):
        raise ValueError(
            f"Schema name '{schema}' contains invalid characters. "
            "Schema names must contain only letters, digits, and underscores."
        )
    return schema


class AsyncSQLDatabase:
    """Async SQLAlchemy wrapper around a PostgreSQL database."""

    def __init__(
        self,
        engine: AsyncEngine,
        schema: Optional[str] = None,
        metadata: Optional[MetaData] = None,
        ignore_tables: Optional[List[str]] = None,
        include_tables: Optional[List[str]] = None,
        sample_rows_in_table_info: int = 3,
        indexes_in_table_info: bool = False,
        custom_table_info: Optional[dict] = None,
        view_support: bool = False,
        max_string_length: int = 300,
    ):
        """Create async engine from database URI."""
        self._engine = engine
        self._schema = schema
        if include_tables and ignore_tables:
            raise ValueError("Cannot specify both include_tables and ignore_tables")

        self._all_tables: set[str] = set()
        self._include_tables = set(include_tables) if include_tables else set()
        self._ignore_tables = set(ignore_tables) if ignore_tables else set()
        self._usable_tables: set[str] = set()

        if not isinstance(sample_rows_in_table_info, int):
            raise TypeError("sample_rows_in_table_info must be an integer")

        self._sample_rows_in_table_info = sample_rows_in_table_info
        self._indexes_in_table_info = indexes_in_table_info

        self._custom_table_info = custom_table_info
        if self._custom_table_info:
            if not isinstance(self._custom_table_info, dict):
                raise TypeError(
                    "table_info must be a dictionary with table names as keys and the "
                    "desired table info as values"
                )

        self._max_string_length = max_string_length
        self._view_support = view_support
        self._metadata = metadata or MetaData()
        self._initialized = False

    async def _initialize(self):
        """Initialize database metadata asynchronously."""
        if self._initialized:
            return

        async with self._engine.connect() as conn:
            if self._schema:
                await conn.execute(
                    text(f"SET search_path TO {sanitize_schema(self._schema)}")
                )

            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
                {"schema": self._schema or "public"},
            )
            tables = [row[0] for row in result.fetchall()]

            if self._view_support:
                result = await conn.execute(
                    text("SELECT viewname FROM pg_views WHERE schemaname = :schema"),
                    {"schema": self._schema or "public"},
                )
                views = [row[0] for row in result.fetchall()]
                self._all_tables = set(tables + views)
            else:
                self._all_tables = set(tables)

            if self._include_tables:
                missing_tables = self._include_tables - self._all_tables
                if missing_tables:
                    raise ValueError(
                        f"include_tables {missing_tables} not found in database"
                    )
            if self._ignore_tables:
                missing_tables = self._ignore_tables - self._all_tables
                if missing_tables:
                    raise ValueError(
                        f"ignore_tables {missing_tables} not found in database"
                    )

            usable_tables = self.get_usable_table_names()
            self._usable_tables = (
                set(usable_tables) if usable_tables else self._all_tables
            )

            if self._custom_table_info:
                intersection = set(self._custom_table_info).intersection(
                    self._all_tables
                )
                self._custom_table_info = dict(
                    (table, self._custom_table_info[table])
                    for table in self._custom_table_info
                    if table in intersection
                )

            await conn.run_sync(
                lambda sync_conn: self._metadata.reflect(
                    views=self._view_support,
                    bind=sync_conn,
                    only=list(self._usable_tables),
                    schema=self._schema,
                )
            )

        self._initialized = True

    @staticmethod
    def from_uri(
        database_uri: Union[str, URL],
        engine_args: Optional[dict] = None,
        **kwargs: Any,
    ) -> "AsyncSQLDatabase":
        """Construct an async SQLAlchemy engine from URI."""
        _engine_args = engine_args or {}
        return AsyncSQLDatabase(
            create_async_engine(database_uri, **_engine_args), **kwargs
        )

    @property
    def dialect(self) -> str:
        """Return string representation of dialect to use."""
        return self._engine.dialect.name

    def get_usable_table_names(self) -> Iterable[str]:
        """Get names of tables available."""
        if self._include_tables:
            return sorted(self._include_tables)
        return sorted(self._all_tables - self._ignore_tables)

    @property
    async def table_info(self) -> str:
        """Information about all tables in the database."""
        return await self.get_table_info()

    async def get_table_info(
        self, table_names: Optional[List[str]] = None, get_col_comments: bool = False
    ) -> str:
        """Get information about specified tables."""
        await self._initialize()

        all_table_names = self.get_usable_table_names()
        if table_names is not None:
            missing_tables = set(table_names).difference(all_table_names)
            if missing_tables:
                raise ValueError(f"table_names {missing_tables} not found in database")
            all_table_names = table_names

        metadata_table_names = [tbl.name for tbl in self._metadata.sorted_tables]
        to_reflect = set(all_table_names) - set(metadata_table_names)
        if to_reflect:
            async with self._engine.connect() as conn:
                await conn.run_sync(
                    lambda sync_conn: self._metadata.reflect(
                        views=self._view_support,
                        bind=sync_conn,
                        only=list(to_reflect),
                        schema=self._schema,
                    )
                )

        meta_tables = [
            tbl
            for tbl in self._metadata.sorted_tables
            if tbl.name in set(all_table_names)
        ]

        tables = []
        for table in meta_tables:
            if self._custom_table_info and table.name in self._custom_table_info:
                tables.append(self._custom_table_info[table.name])
                continue

            try:
                for k, v in table.columns.items():
                    if type(v.type) is NullType:
                        table._columns.remove(v)
            except AttributeError:
                for k, v in dict(table.columns).items():
                    if type(v.type) is NullType:
                        table._columns.remove(v)

            async with self._engine.connect() as conn:
                create_table = await conn.run_sync(
                    lambda sync_conn: str(CreateTable(table).compile(sync_conn))
                )
            table_info = f"{create_table.rstrip()}"

            if get_col_comments:
                try:
                    column_comments_dict = {}
                    for column in table.columns:
                        if column.comment:
                            column_comments_dict[column.name] = column.comment

                    if column_comments_dict:
                        table_info += (
                            f"\n\n/*\nColumn Comments: {column_comments_dict}\n*/"
                        )
                except Exception:
                    raise ValueError(
                        "Column comments are available on PostgreSQL, MySQL, Oracle"
                    )

            has_extra_info = (
                self._indexes_in_table_info or self._sample_rows_in_table_info
            )
            if has_extra_info:
                table_info += "\n\n/*"
            if self._indexes_in_table_info:
                table_info += f"\n{await self._get_table_indexes(table)}\n"
            if self._sample_rows_in_table_info:
                table_info += f"\n{await self._get_sample_rows(table)}\n"
            if has_extra_info:
                table_info += "*/"
            tables.append(table_info)
        tables.sort()
        final_str = "\n\n".join(tables)
        return final_str

    async def _get_table_indexes(self, table: Table) -> str:
        """Get table indexes asynchronously."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT 
                        i.relname as name,
                        ix.indisunique as unique,
                        ARRAY_AGG(a.attname ORDER BY a.attnum) as column_names
                    FROM pg_class t
                    JOIN pg_index ix ON t.oid = ix.indrelid
                    JOIN pg_class i ON i.oid = ix.indexrelid
                    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                    WHERE t.relname = :table_name
                    AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = :schema)
                    GROUP BY i.relname, ix.indisunique
                """),
                {"table_name": table.name, "schema": self._schema or "public"},
            )
            indexes = []
            for row in result.fetchall():
                indexes.append(
                    {"name": row[0], "unique": row[1], "column_names": row[2]}
                )

        indexes_formatted = "\n".join(map(_format_index, indexes))
        return f"Table Indexes:\n{indexes_formatted}"

    async def _get_sample_rows(self, table: Table) -> str:
        """Get sample rows from table asynchronously."""
        command = select(table).limit(self._sample_rows_in_table_info)
        columns_str = "\t".join([col.name for col in table.columns])

        try:
            async with self._engine.connect() as connection:
                sample_rows_result = await connection.execute(command)
                sample_rows = list(
                    map(
                        lambda ls: [str(i)[:100] for i in ls],
                        sample_rows_result.fetchall(),
                    )
                )

            sample_rows_str = "\n".join(["\t".join(row) for row in sample_rows])

        except ProgrammingError:
            sample_rows_str = ""

        return (
            f"{self._sample_rows_in_table_info} rows from {table.name} table:\n"
            f"{columns_str}\n"
            f"{sample_rows_str}"
        )

    async def _execute(
        self,
        command: Union[str, Executable],
        fetch: Literal["all", "one", "cursor"] = "all",
        *,
        parameters: Optional[Dict[str, Any]] = None,
        execution_options: Optional[Dict[str, Any]] = None,
    ) -> Union[Sequence[Dict[str, Any]], Result]:
        """Execute SQL command through DatabaseSession."""
        parameters = parameters or {}
        execution_options = execution_options or {}

        async with DatabaseSession() as session:
            if self._schema is not None:
                await session.execute(
                    text("SET search_path TO :schema"),
                    {"schema": self._schema},
                )

            if isinstance(command, str):
                command = text(command)
            elif isinstance(command, Executable):
                pass
            else:
                raise TypeError(f"Query expression has unknown type: {type(command)}")

            cursor = await session.execute(
                command,
                parameters,
            )

            if cursor.returns_rows:
                if fetch == "all":
                    result = [x._asdict() for x in cursor.fetchall()]
                elif fetch == "one":
                    first_result = cursor.fetchone()
                    result = [] if first_result is None else [first_result._asdict()]
                elif fetch == "cursor":
                    return cursor
                else:
                    raise ValueError(
                        "Fetch parameter must be either 'one', 'all', or 'cursor'"
                    )
                return result
        return []

    async def run(
        self,
        command: Union[str, Executable],
        fetch: Literal["all", "one", "cursor"] = "all",
        include_columns: bool = False,
        *,
        parameters: Optional[Dict[str, Any]] = None,
        execution_options: Optional[Dict[str, Any]] = None,
    ) -> Union[str, Sequence[Dict[str, Any]], Result[Any]]:
        """Execute a SQL command and return a string representing the results."""
        result = await self._execute(
            command, fetch, parameters=parameters, execution_options=execution_options
        )

        if fetch == "cursor":
            return result

        res = [
            {
                column: truncate_word(value, length=self._max_string_length)
                for column, value in r.items()
            }
            for r in result
        ]

        if not include_columns:
            res = [tuple(row.values()) for row in res]

        if not res:
            return ""
        else:
            return res

    async def get_table_info_no_throw(
        self, table_names: Optional[List[str]] = None
    ) -> str:
        """Get information about specified tables without throwing exceptions."""
        try:
            return await self.get_table_info(table_names)
        except ValueError as e:
            return f"Error: {e}"

    async def run_no_throw(
        self,
        command: str,
        fetch: Literal["all", "one"] = "all",
        include_columns: bool = False,
        *,
        parameters: Optional[Dict[str, Any]] = None,
        execution_options: Optional[Dict[str, Any]] = None,
    ) -> Union[str, Sequence[Dict[str, Any]], Result[Any]]:
        """Execute a SQL command and return a string representing the results without throwing exceptions."""
        try:
            return await self.run(
                command,
                fetch,
                parameters=parameters,
                execution_options=execution_options,
                include_columns=include_columns,
            )
        except SQLAlchemyError as e:
            logger.error(f"Error executing command: {command}, error: {e}")
            return f"Error: {e}"

    async def get_context(self) -> Dict[str, Any]:
        """Return db context that you may want in agent prompt."""
        await self._initialize()
        table_names = list(self.get_usable_table_names())
        table_info = await self.get_table_info_no_throw()
        return {"table_info": table_info, "table_names": ", ".join(table_names)}
