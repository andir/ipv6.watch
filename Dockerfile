FROM python:3.6-stretch

ADD requirements.txt run.py /code/
WORKDIR /code
RUN pip install -r requirements.txt
ADD templates /code/templates
ADD dist /code/dist
ADD conf.yaml /code/
EXPOSE 8080
CMD python run.py serve
