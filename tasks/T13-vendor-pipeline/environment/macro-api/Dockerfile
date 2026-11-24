FROM deliverbench-base:0.1.0
USER root
RUN mkdir -p /srv/log
COPY macro_api.py data.json /srv/
CMD ["python", "-u", "/srv/macro_api.py", "--data", "/srv/data.json", "--port", "8090", "--log", "/srv/log/api.log"]
