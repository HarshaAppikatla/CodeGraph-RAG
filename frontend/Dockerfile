FROM node:20-alpine

WORKDIR /app

# Install project dependencies
COPY package*.json ./
RUN npm install

# Copy application source code
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
