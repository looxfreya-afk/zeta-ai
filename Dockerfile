FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 ZETA_HOME=/data ZETA_HOST=0.0.0.0 PORT=8787
WORKDIR /app
COPY zeta.py .
RUN useradd -m zeta && mkdir /data && chown zeta /data
USER zeta
VOLUME /data
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request as u;u.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8787')+'/healthz',timeout=4)" || exit 1
CMD ["python", "zeta.py", "--admin"]
