FROM python:3.11
LABEL maintainer="JanneK"
# Copy only requirements.txt first to leverage Docker cache
COPY requirements.txt requirements.txt
COPY mysurvey.py mysurvey.py
COPY .env .env
RUN pip install -r requirements.txt
#Copy files to your container
COPY app.py ./app.py
# Running your APP and doing some PORT Forwarding
EXPOSE 8080
CMD gunicorn -w 4 -b 0.0.0.0:8080 app:server