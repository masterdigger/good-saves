# Good Saves

En modul för att hantera och skicka formulärdata med dynamiska värden.

## Installation

```bash
git clone https://github.com/masterdigger/good-saves.git
cd good-saves
poetry install
```

## Användning

```python
from good_saves.main import main_function

main_function()
```

## Commit

Bidrag är välkomna! Vänligen öppna en issue eller skicka in en pull request.

## Usage

### Initialization

To initialize the package, you need to import the necessary modules and set up the logger.

```python
from config.logger_config import setup_logger
from http_client import HTTPClient
from form_handler import FormHandler
from cookie_handler import CookieHandler

logger = setup_logger()
```

### Configuration

Ensure that your configuration files (`config.json` and `postdata.json`) are located in the `config` directory.

### Running the Application

To run the application, use the following code:

```python
from config.logger_config import setup_logger
from http_client import HTTPClient
from form_handler import FormHandler
from cookie_handler import CookieHandler

logger = setup_logger()

if __name__ == "__main__":
    logger.info("Starting application.")

    try:
        with HTTPClient(base_url=BASE_URL, headers_list=HEADERS_LIST) as client:
            logger.info("HTTPClient initialized successfully.")

            response = client.get(PATH, params=QUERY_PARAMS)
            logger.info("Initial GET request successful.")

            soup = BeautifulSoup(response.text, "html.parser")
            form_handler = FormHandler(client=client, form_data=FormData(data={}), path=PATH, query_params=QUERY_PARAMS)

            form_handler.parse_cookie(soup)
            logger.info("Cookies parsed and set.")

            post_response = form_handler.submit_form()
            if post_response:
                logger.info(f"Form submitted successfully. Response: {post_response.text[:100]}...")
            else:
                logger.warning("No response received after form submission.")

    except Exception as e:
        logger.critical(f"Application terminated due to an error: {e}")
```

### Dependencies

Ensure that you have the necessary dependencies installed. You can find the dependencies in the `pyproject.toml` file.

### Contributing

Contributions are welcome! Please open an issue or submit a pull request.
