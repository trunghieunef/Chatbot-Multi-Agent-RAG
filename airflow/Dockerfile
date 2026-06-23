FROM apache/airflow:2.10.3-python3.11

ARG AIRFLOW_VERSION=2.10.3
ARG PYTHON_VERSION=3.11
ENV AIRFLOW_CONSTRAINTS_URL=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt

USER airflow
COPY airflow/requirements.txt /requirements.txt
RUN pip install --timeout 300 --retries 10 -r /requirements.txt --constraint "${AIRFLOW_CONSTRAINTS_URL}"
