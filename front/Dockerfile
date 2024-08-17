FROM node:18.13.0-alpine
ENV NODE_ENV development

WORKDIR /front
#COPY . /front/
# add `/app/node_modules/.bin` to $PATH
ENV PATH /front/node_modules/.bin:$PATH

# install app dependencies
COPY package.json ./
COPY package-lock.json ./
RUN npm install

# add app
COPY . ./

EXPOSE 3000
# start app
CMD ["npm", "start"]
