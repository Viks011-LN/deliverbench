FROM deliverbench-base:0.1.0
USER root
COPY server.py data.json notes.md /srv/
CMD ["python", "-u", "/srv/server.py"]
