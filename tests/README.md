# Zappa Test Notes

Look here!: https://github.com/garnaat/placebo#usage-as-a-decorator

Also useful - OSX sed replace example:

`
find . -type f -name '*.json' -exec sed -i '' s/"Resource%22%3A%20%22arn%3Aaws%3Asqs%3A%3A%3A%2A%22%0A%20%20%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%20%20%20%20%7B%0A%20%20%20%20%20%20%20%20%20%20%20%20%22Effect"/"Resource%22%3A%20%22arn%3Aaws%3Asqs%3A*%3A*%3A*%22%0A%20%20%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%20%20%20%20%7B%0A%20%20%20%20%20%20%20%20%20%20%20%20%22Effect"/ {} +
`
