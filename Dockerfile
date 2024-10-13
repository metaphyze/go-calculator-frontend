# Dockerfile for Flask app
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy application code
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
#RUN pip install flask
#RUN pip install requests
#RUN pip freeze > requirements.txt

# Expose the Flask port
EXPOSE 5000

ENV PORT=5000
ENV CALCULATION_URL=http://localhost:9999

# Run the Flask app
CMD ["python", "app.py"]

