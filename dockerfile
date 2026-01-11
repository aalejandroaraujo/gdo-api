FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    FUNCTIONS_WORKER_RUNTIME=python

COPY requirements.txt /
RUN pip install -r /requirements.txt

# Copy application files
COPY function_app.py /home/site/wwwroot/
COPY host.json /home/site/wwwroot/
COPY src/ /home/site/wwwroot/src/
