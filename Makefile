planets_source = https://raw.githubusercontent.com/devstronomy/nasa-data-scraper/master/data/json/planets.json
satellites_source = https://raw.githubusercontent.com/devstronomy/nasa-data-scraper/master/data/json/satellites.json
wikidata_sparql_endpoint = https://query.wikidata.org/sparql

data/temp/wikidata_planets.json: data/temp
	@echo "querying $(wikidata_sparql_endpoint) for planets ..."
	@echo "writing to $@ ..."
	@rqw -f queries/planets_of_the_solar_system.rq -e $(wikidata_sparql_endpoint) > $@

data/temp/wikidata_moons.json: data/temp
	@echo "querying $(wikidata_sparql_endpoint) for planets ..."
	@echo "writing to $@ ..."
	@rqw -f queries/moons_of_the_solar_system.rq -e $(wikidata_sparql_endpoint) > $@

data/solar_system.ttl: data data/temp/wikidata_planets.json data/temp/wikidata_moons.json
	@echo "converting source data to $@ ..."
	@python bin/planets2rdf.py --base https://berlinonline.github.io/lod-browser/ --source data/temp --output $@

clean: clean-temp

clean-temp:
	@echo "deleting temp folder ..."
	@rm -rf data/temp

data:
	@echo "creating $@ directory ..."
	mkdir -p $@

data/temp: data
	@echo "creating $@ directory ..."
	@mkdir -p $@

