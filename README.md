# alertmanager-karma

## Description

TODO: Describe your charm in a few paragraphs of Markdown

## Usage

TODO: Provide high-level usage, such as required config or relations

juju deploy ./alertmanager-karma.charm --resource karma-image=ghcr.io/prymitive/karma:v0.86

## Developing

Create and activate a virtualenv with the development requirements:

```bash
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

```bash
    ./run_tests
```

## Roadmap

* TLS support
* Authentication
* Relation to Alertmanager
