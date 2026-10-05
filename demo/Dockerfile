FROM python:3.12-alpine
WORKDIR /app
COPY app.py /app/app.py
COPY ui.py /app/ui.py
COPY seed_state.json /app/seed_state.json
COPY start.sh /app/start.sh
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "/app/start.sh"]
