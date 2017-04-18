default: build flake8 push

build:
	docker-compose build app

flake8:
	docker-compose run --rm app flake8 src

push:
	docker-compose push app
