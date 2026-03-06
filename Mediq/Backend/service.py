from sqlalchemy import text, bindparam
import traceback
from config import TABLE_SCHEMA,log_execution
from sqlalchemy.exc import SQLAlchemyError
from config import logger


@log_execution(is_api=False)
async def mediq_search(engine, question:str) -> dict:
        """
        Performs a vector search to find medical details.

        Args:
            question (str): The user's search query.

        Returns:
            A dictionary with a 'summary' and 'details' for matching products.
        """
        query = text(f"""SELECT * FROM {TABLE_SCHEMA}.search_medical_info(:question);""")
        try:
            with engine.connect() as connection:
                logger.info(f"Database connection established for vector search.")
                result = connection.execute(query, {"question": question})
                rows = result.fetchall()
                search_results = [dict(r._mapping) for r in rows]
                query = query.bindparams(bindparam("question", value=question))
                compiled = query.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
                sql_string = str(compiled)
                if not rows:
                    logger.warning("No results returned from query.")
                    return {
                        "sql_command": sql_string, "summary": "No results found for the selected search!",
                    }
                logger.info(f"Query executed successfully for vector search.")
                return {"sql_command": sql_string, "details":search_results} 

        except SQLAlchemyError as e:
            traceback_details = traceback.format_exc()
            logger.error(f"Database error occurred!! :: {str(e)}, traceback {traceback_details}")
            return {"error": f"Database error: {str(e)}","traceback":traceback_details}

        except Exception as e:
            traceback_details = traceback.format_exc()
            logger.error(f"Error occured during search!! :: {str(e)}, traceback {traceback_details}")
            return {"error":f"Error occured during search : {e}","traceback":traceback_details}