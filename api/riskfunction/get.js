// Load the AWS SDK for Node.js
const AWS = require('aws-sdk')
// Set region
AWS.config.update({region: 'us-west-2'})
// Create S3 service
const S3 = new AWS.S3({apiVersion: '2006-03-01'})
// Define headers
const headers = {
  "Content-Type": "application/json",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
}
// Lambda handler
exports.handler = async function(event) {
  return new Promise((resolve, reject) => {
    resolve({
      statusCode: 200,
      headers: headers,
      body: "data goes here"
    })
  })
}
