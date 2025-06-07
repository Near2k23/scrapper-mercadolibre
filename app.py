import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from urllib.parse import unquote, urlparse
import json
# import pandas

app = Flask(__name__)
CORS(app)
app.config['JSON_AS_ASCII'] = False

def is_valid_image_url(url):
    """Verifica si una URL de imagen es válida"""
    if not url:
        return False
    if url.startswith('data:image'):
        return False
    if url.endswith('.gif'):
        return False
    return True

def clean_text(text):
    """Limpia y normaliza el texto a UTF-8"""
    if not text:
        return None
    return text.encode('utf-8').decode('utf-8')

def is_valid_meli_url(url):
    """Verifica si es una URL válida de Mercado Libre Colombia"""
    parsed_url = urlparse(url)
    valid_domains = [
        'articulo.mercadolibre.com.co',
        'listado.mercadolibre.com.co',
        'www.mercadolibre.com.co'
    ]
    return parsed_url.netloc in valid_domains

def normalize_meli_url(url):
    """Normaliza la URL de Mercado Libre eliminando parámetros innecesarios"""
    parsed_url = urlparse(url)
    # Si es una URL de producto individual en www.mercadolibre.com.co
    if parsed_url.netloc == 'www.mercadolibre.com.co':
        # Eliminar parámetros de tracking y mantener solo la ruta base
        path = parsed_url.path
        if '#' in url:
            path = path.split('#')[0]
        return f"https://{parsed_url.netloc}{path}"
    return url

def extract_price(soup):
    """Extrae el precio normal y con descuento"""
    price_data = {
        "regular_price": None,
        "discount_price": None,
        "discount_percentage": None,
        "installments": {
            "quantity": None,
            "amount": None,
            "interest": None
        }
    }
    
    # Buscar contenedor principal de precios
    price_container = soup.find('div', class_='ui-pdp-price__main-container')
    if not price_container:
        # Si no encuentra el contenedor principal, buscar en el listado
        price_elem = soup.find('span', class_='andes-money-amount__fraction')
        if price_elem:
            price_data["discount_price"] = float(price_elem.text.replace('.', '').replace(',', '.'))
            price_data["regular_price"] = price_data["discount_price"]
        return price_data

    # Buscar precio original (tachado)
    original_price_elem = price_container.find('s', class_='andes-money-amount--previous')
    if original_price_elem:
        price_fraction = original_price_elem.find('span', class_='andes-money-amount__fraction')
        if price_fraction:
            price_text = price_fraction.text.strip()
            price_data["regular_price"] = float(price_text.replace('.', '').replace(',', '.'))

    # Buscar precio con descuento (precio actual)
    current_price_elem = price_container.find('span', {'class': 'andes-money-amount', 'style': 'font-size:36px'})
    if current_price_elem:
        price_fraction = current_price_elem.find('span', class_='andes-money-amount__fraction')
        if price_fraction:
            price_text = price_fraction.text.strip()
            price_data["discount_price"] = float(price_text.replace('.', '').replace(',', '.'))
    
    # Si no hay precio con descuento pero hay precio regular, usar el mismo
    if not price_data["discount_price"] and price_data["regular_price"]:
        price_data["discount_price"] = price_data["regular_price"]
    # Si hay precio con descuento pero no hay precio regular, usar el mismo
    elif price_data["discount_price"] and not price_data["regular_price"]:
        price_data["regular_price"] = price_data["discount_price"]
    
    # Buscar porcentaje de descuento
    discount_elem = price_container.find('span', class_='andes-money-amount__discount')
    if discount_elem:
        discount_text = discount_elem.text.replace('% OFF', '').replace('%', '').strip()
        try:
            price_data["discount_percentage"] = int(discount_text)
        except:
            pass
    
    # Buscar información de cuotas
    installments_elem = price_container.find('p', id='pricing_price_subtitle')
    if installments_elem:
        # Extraer cantidad de cuotas
        installment_text = installments_elem.get_text()
        if 'cuotas' in installment_text:
            try:
                quantity = int(installment_text.split('cuotas de')[0].strip().split()[-1])
                price_data["installments"]["quantity"] = quantity
            except:
                pass
            
            # Extraer monto de cuota
            amount_elem = installments_elem.find('span', class_='andes-money-amount__fraction')
            if amount_elem:
                try:
                    amount = float(amount_elem.text.strip().replace('.', '').replace(',', '.'))
                    price_data["installments"]["amount"] = amount
                except:
                    pass
            
            # Extraer información de interés
            if '0% interés' in installment_text:
                price_data["installments"]["interest"] = 0
            elif 'interés' in installment_text:
                try:
                    interest = int(installment_text.split('interés')[0].strip().split()[-1].replace('%', ''))
                    price_data["installments"]["interest"] = interest
                except:
                    pass
    
    return price_data

def extract_variations(soup):
    """Extrae las variaciones del producto (colores, tamaños, etc.)"""
    variations = {
        "colors": []
    }
    
    variations_container = soup.find('div', class_='ui-pdp-variations')
    if variations_container:
        # Buscar todas las variaciones (thumbnails)
        thumbnails = variations_container.find_all('a', class_='ui-pdp-thumbnail')
        for thumbnail in thumbnails:
            # Extraer información de cada variación
            img = thumbnail.find('img', class_='ui-pdp-image')
            img_url = None
            
            if img:
                # Primero intentar obtener la URL 2x del srcset
                srcset = img.get('srcset', '')
                if srcset:
                    urls = srcset.split(',')
                    for url in urls:
                        if '2x' in url and '.webp' in url:
                            img_url = url.strip().split(' ')[0]
                            break
                
                # Si no se encontró en srcset, intentar con data-zoom
                if not img_url:
                    img_url = img.get('data-zoom')
                
                # Si aún no hay URL, intentar con src
                if not img_url:
                    img_url = img.get('src')
                
                # Asegurarse de que la URL no sea base64 o gif
                if img_url and (img_url.startswith('data:') or img_url.endswith('.gif')):
                    img_url = None
            
            variation = {
                "name": img.get('alt') if img else None,
                "url": thumbnail.get('href') if thumbnail else None,
                "image": img_url,
                "selected": 'ui-pdp-thumbnail--SELECTED' in thumbnail.get('class', [])
            }
            variations["colors"].append(variation)
    
    return variations if variations["colors"] else None

def extract_specifications(soup):
    """Extrae las especificaciones técnicas del producto"""
    specs = {}
    
    # Buscar la sección de especificaciones
    specs_section = soup.find('div', class_='ui-pdp-container__row--technical-specifications')
    if specs_section:
        # Buscar todas las tablas de especificaciones
        tables = specs_section.find_all('table', class_='andes-table')
        for table in tables:
            rows = table.find_all('tr', class_='andes-table__row')
            for row in rows:
                header = row.find('th')
                value = row.find('td')
                if header and value:
                    key = clean_text(header.get_text(strip=True))
                    val = clean_text(value.get_text(strip=True))
                    specs[key] = val
    
    return specs

# GET Request
@app.route('/web-scrapper', methods=["GET"])
def webScrapper():
    try:
        # Intentar obtener datos de diferentes fuentes
        if request.is_json:
            data = request.get_json()
        elif request.args:
            data = request.args.to_dict()
        else:
            return Response(
                json.dumps({
                    "error": "No se proporcionaron parámetros. Use 'producto' y 'limit' como parámetros"
                }, ensure_ascii=False),
                status=400,
                content_type='application/json; charset=utf-8'
            )

        # Establecer límite predeterminado
        limit = int(data.get("limit", 15))

        # Obtener y validar la URL del producto
        producto = data.get("producto")
        if not producto:
            return Response(
                json.dumps({
                    "error": "Se requiere el parámetro 'producto' con la URL de Mercado Libre"
                }, ensure_ascii=False),
                status=400,
                content_type='application/json; charset=utf-8'
            )

        url = unquote(producto)
        
        # Verificar si es una URL válida de Mercado Libre Colombia
        if not is_valid_meli_url(url):
            return Response(
                json.dumps({
                    "error": "La URL debe ser de Mercado Libre Colombia"
                }, ensure_ascii=False),
                status=400,
                content_type='application/json; charset=utf-8'
            )

        # Normalizar la URL
        url = normalize_meli_url(url)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(url, headers=headers)
        res.encoding = 'utf-8'
        
        if res.status_code == 200:
            html_content = res.content
            soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')

            titles = []
            prices = []
            urls = []
            images = []
            descriptions = []
            specifications = []
            variations = []

            # Si es una página de listado
            if 'listado.mercadolibre.com' in url:
                products_page = soup.find_all('li', class_='ui-search-layout__item')

                for index, product in enumerate(products_page):
                    if index >= limit:
                        break
                    
                    title = product.find('h2', class_='ui-search-item__title')
                    product_url = product.find('a', class_='ui-search-item__group__element')
                    
                    # Extraer precios
                    price_data = extract_price(product)
                    
                    # Buscar imagen en diferentes atributos y clases
                    image_url = None
                    img_elem = product.find('img', {'class': ['ui-search-result-image__element']})
                    if img_elem:
                        # Intentar diferentes atributos de imagen
                        for attr in ['data-src', 'src']:
                            if img_elem.get(attr) and is_valid_image_url(img_elem[attr]):
                                image_url = img_elem[attr].replace('http:', 'https:')
                                break
                    
                    if title and product_url:
                        titles.append(clean_text(title.text))
                        prices.append(price_data)
                        urls.append(product_url['href'])
                        images.append(image_url)
                        descriptions.append(None)
                        specifications.append(None)
                        variations.append(None)
            
            # Si es una página de producto individual
            else:
                title = soup.find('h1', class_='ui-pdp-title')
                
                # Extraer precios
                price_data = extract_price(soup)
                
                # Buscar imágenes en la galería
                gallery_images = []
                gallery = soup.find('div', class_='ui-pdp-gallery')
                if gallery:
                    for img in gallery.find_all('figure', class_='ui-pdp-gallery__figure'):
                        img_elem = img.find('img', class_='ui-pdp-image')
                        if img_elem and img_elem.get('data-zoom'):
                            url_img = img_elem['data-zoom'].replace('http:', 'https:')
                            if is_valid_image_url(url_img):
                                gallery_images.append(url_img)
                
                # Buscar descripción
                description = None
                desc_elem = soup.find('p', class_='ui-pdp-description__content')
                if desc_elem:
                    description = clean_text(desc_elem.text.strip())
                
                # Extraer especificaciones y variaciones
                specs = extract_specifications(soup)
                product_variations = extract_variations(soup)
                
                if title:
                    titles.append(clean_text(title.text))
                    prices.append(price_data)
                    urls.append(url)
                    images.append(gallery_images if gallery_images else None)
                    descriptions.append(description)
                    specifications.append(specs)
                    variations.append(product_variations)

            if not titles:
                return Response(
                    json.dumps({
                        "error": "No se encontraron productos"
                    }, ensure_ascii=False),
                    status=404,
                    content_type='application/json; charset=utf-8'
                )

            return Response(
                json.dumps({
                    "data": {
                        "Titles": titles,
                        "Prices": prices,
                        "URLs": urls,
                        "Images": images,
                        "Descriptions": descriptions,
                        "Specifications": specifications,
                        "Variations": variations
                    }
                }, ensure_ascii=False),
                content_type='application/json; charset=utf-8'
            )
        
        else:
            return Response(
                json.dumps({
                    "error": f"Error al acceder a la URL proporcionada. Código: {res.status_code}"
                }, ensure_ascii=False),
                status=res.status_code,
                content_type='application/json; charset=utf-8'
            )

    except Exception as e:
        return Response(
            json.dumps({
                "error": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False),
            status=500,
            content_type='application/json; charset=utf-8'
        )

# POST Request
@app.route('/search', methods=["GET", "POST"])
def webScrapperSearch():
    if request.method == "POST":
        data = request.json
        url = data.get("producto")
        limit = data.get("limit", 10)

        if not url:
            return jsonify({"error": "Se requiere el parámetro 'producto' con la URL de Mercado Libre"}), 400

        response = requests.get(
            "http://localhost:5000/web-scrapper",
            data=json.dumps({"producto": url, "limit": int(limit)}),
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"error": "Ha ocurrido un error, por favor intente más tarde"}), response.status_code

    return jsonify({"error": "Este endpoint solo acepta solicitudes POST"}), 405

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)