import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

import json
# import pandas

app = Flask(__name__)

# GET Request
@app.route('/web-scrapper', methods=["GET"])
def webScrapper():
    data = json.loads(request.data)

    if "limit" not in data:
        limit = 15
    else:
        limit = data["limit"]

    # data = input("Ingresar producto: \n")
    # limit = int(input("Ingresar cantidad máxima de productos a buscar: \n"))

    res = requests.get("https://listado.mercadolibre.com.ar/{}#D[A:{}]".format(data["product"].replace(" ", "-"), data["product"]))

    if res.status_code == 200:
        html_content = res.content
        soup = BeautifulSoup(html_content, 'html.parser')

        titles = []
        prices = []
        urls = []

        products_page = soup.find_all('li', class_='ui-search-layout__item')

        for index, product in enumerate(products_page):
            if index >= limit:
                break
            
            title = product.find('h2', class_='ui-search-item__title').text
            price = product.find('span', class_='andes-money-amount__fraction').text
            url = product.find('a', class_='ui-search-item__group__element')['href']
            
            if title and url and price:
                titles.append(title)
                prices.append(float(price.replace('.', '').replace(',', '.')))
                urls.append(url)

        average_price = sum(prices) / len(prices) if len(prices) > 0 else 0
        average_price_rounded = round(average_price, 2)

        # Data:
        print('\n---')
        print(f'Precio Promedio: ${average_price_rounded}')
        print('---')

        for i in range(len(titles)):
            print("\n" + f'Título: {titles[i]}')
            print(f'URL: {urls[i]}')
            print(f'Precio: ${prices[i]}')
            print('\n ---')

        # If you like to use `pandas`:
        # table_df = pandas.DataFrame({"Título": titles, "Precio": prices, "URLs": urls})
        # table_df
    
    else:
        print("An error has ocurred, please try again later.")

    return jsonify({"data":{"Titles": titles, "Prices": prices , "URLs": urls }, "average_price": average_price_rounded})

# POST Request
@app.route('/search', methods=["GET", "POST"])
def webScrapperSearch():
    if request.method == "POST":
        data = request.json
        product = data.get("product")
        limit = data.get("limit", 10)

        response = requests.get("http://localhost:5000/web-scrapper", data=json.dumps({"product": product, "limit": int(limit)}), headers={"Content-Type": "application/json"})
        print(response.status_code)

        if response.status_code == 200:
            data = response.json()
            return jsonify(data)
        else:
            return "An error has occurred, please try again later."

    return "This endpoint only accepts POST requests."

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)