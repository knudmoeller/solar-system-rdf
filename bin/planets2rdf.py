import argparse
import hashlib
import json
import logging
import requests
from pathlib import Path
from slugify import slugify
from urllib.parse import quote, unquote, urljoin
from rdflib import Graph, Literal, RDF, RDFS, URIRef, Namespace, BNode, XSD

LOG = logging.getLogger(__name__)

schema = Namespace("https://schema.org/")
wikidata = Namespace("http://www.wikidata.org/entity/")

def get_image_name(image_url: str):
    image_name = image_url.removeprefix('http://commons.wikimedia.org/wiki/Special:FilePath/')
    return unquote(image_name)

def get_wc_metadata(image_name: str):
    response = requests.get(f'https://commons.wikimedia.org/w/api.php?action=query&titles=Image:{image_name}&prop=imageinfo&iiprop=extmetadata&format=json')
    return response.json()

# function from https://stackoverflow.com/a/64323021/9539770
def get_wc_thumb(image_name: str, width=300): # image = e.g. from Wikidata, width in pixels
    image_name = image_name.replace(' ', '_') # need to replace spaces with underline
    m = hashlib.md5()
    m.update(image_name.encode('utf-8'))
    d = m.hexdigest()
    return "https://upload.wikimedia.org/wikipedia/commons/thumb/"+d[0]+'/'+d[0:2]+'/'+quote(image_name)+'/'+str(width)+'px-'+quote(image_name)

def means_unknown(url):
    return ".well-known/genid/" in url

class SpaceConverter:

    def __init__(self, args):
        self.args = args
        base = args.base
        self.graph = Graph()
        self.space = Namespace(base)
        self.spacevoc = Namespace(urljoin(base, "spacevoc/"))
        self.quantitative_values = []
    
    def add_image(self, result, key: str, resource: URIRef):
        space = self.space
        statement_key = hashlib.md5(f"{resource.toPython}-{key}".encode("utf-8")).hexdigest()
        if not statement_key in self.quantitative_values:
            graph = self.graph
            if key in result:
                # extract image metadata: 
                # https://commons.wikimedia.org/w/api.php?action=query&titles=Image:Commons-logo.svg&prop=imageinfo&iiprop=extmetadata
                image_res = BNode()
                graph.add( (image_res, RDF.type, schema.VisualArtwork) )
                image_name = get_image_name(result[key]['value'])
                graph.add( (image_res, schema.url, URIRef(f"https://commons.wikimedia.org/wiki/File:{quote(image_name)}")) )
                print(image_name)
                preview_url = get_wc_thumb(image_name, 200)
                graph.add( (image_res, schema.thumbnail, URIRef(preview_url)) )

                wikicommons_metadata = get_wc_metadata(image_name)
                pages = wikicommons_metadata['query']['pages']
                page = next(iter(pages.values()))
                ext_metadata = page['imageinfo'][0]['extmetadata']
                license_label = ext_metadata['LicenseShortName']['value']
                license_id = f"lic_{slugify(license_label)}"
                license_res = URIRef(space[license_id])
                if 'LicenseShortName' in ext_metadata:
                    graph.add( (image_res, schema.license, license_res) )
                    graph.add( (license_res, schema.name, Literal(ext_metadata['LicenseShortName']['value'])) )
                if 'LicenseUrl' in ext_metadata:
                    graph.add( (image_res, schema.license, license_res) )
                    graph.add( (license_res, schema.url, URIRef(ext_metadata['LicenseUrl']['value'])) )

                if 'Artist' in ext_metadata:
                    # TODO: schema.creator should link to an instance of Person, but common's 'Artist' 
                    # gives an HTML snippet with a link to a user page
                    graph.add( (image_res, schema.creator, Literal(ext_metadata['Artist']['value'])) )
                if 'Credit' in ext_metadata:
                    graph.add( (image_res, schema.creditText, Literal(ext_metadata['Credit']['value'])) )

                graph.add( (resource, schema.image, image_res) )
                self.quantitative_values.append(statement_key)

    def add_discoverer(self, result, resource: URIRef):
        graph = self.graph
        space = self.space
        spacevoc = self.spacevoc
        key = 'discoverer'
        if key in result:
            discoverer_uri = result[key]['value']
            if not means_unknown(discoverer_uri):
                discoverer_name = result[f"{key}Label"]['value']
                discoverer_id = slugify(discoverer_name)
                discoverer_res = space[f"person_{discoverer_id}"]
                graph.add( (resource, spacevoc.discoverer, discoverer_res) )
                graph.add( (discoverer_res, RDF.type, schema.Person) )
                graph.add( (discoverer_res, schema.name, Literal(discoverer_name)) )
                graph.add( (discoverer_res, schema.sameAs, URIRef(discoverer_uri)) )

    def add_discovery_date(self, result, resource: URIRef):
        graph = self.graph
        spacevoc = self.spacevoc
        if 'time_of_discovery' in result:
            date_string = result['time_of_discovery']['value']
            if not means_unknown(date_string):
                date_type = XSD.date
                graph.add( (resource, spacevoc.time_of_discovery, Literal(date_string[0:10], datatype=date_type)))

    def add_quantitative_value(self, resource: URIRef, property: URIRef, cefact_code: str, value):
        statement_key = hashlib.md5(f"{resource.toPython}-{value}-{cefact_code}".encode("utf-8")).hexdigest()
        if not statement_key in self.quantitative_values:
            graph = self.graph
            value_node = BNode()
            graph.add( (resource, property, value_node) )
            graph.add( (value_node, RDF.type, schema.QuantitativeValue) )
            graph.add( (value_node, schema.value, Literal(value)) )
            graph.add( (value_node, schema.unitCode, Literal(cefact_code)) )
            self.quantitative_values.append(statement_key)


    def convert(self):
        args = self.args
        graph = self.graph
        space = self.space
        spacevoc = self.spacevoc

        # convert planet data
        wikidata_planets_path = args.source / "wikidata_planets.json"
        with open(wikidata_planets_path) as wikidata_planets_file:
            wikidata_planets = json.load(wikidata_planets_file)

            # start with the sun
            sun_name = "Sun"
            sun_id = f"s_{slugify(sun_name)}"
            sun_res = space[sun_id]
            graph.add( (sun_res, RDF.type, spacevoc.Star) )
            graph.add( (sun_res, RDFS.label, Literal(sun_name, lang="en")) )
            graph.add( (sun_res, schema.sameAs, wikidata['Q525']) )

            for result in wikidata_planets['results']['bindings']:
                planet_name = result['planetLabel']['value']
                planet_id = f"p_{slugify(planet_name)}"
                planet_res = space[planet_id]
                planet_type = spacevoc.Planet
                if planet_name == "Pluto":
                    planet_type = spacevoc.DwarfPlanet
                graph.add( (planet_res, RDF.type, planet_type) )
                
                graph.add( (planet_res, RDFS.label, Literal(planet_name, lang="en")) )
                graph.add( (planet_res, spacevoc.orbits, sun_res) )
                wikidata_url = result['planet']['value']
                graph.add( (planet_res, schema.sameAs, URIRef(wikidata_url)) )

                self.add_image(result, 'planet_image', planet_res)

                self.add_discoverer(result, planet_res)
                self.add_discovery_date(result, planet_res)

                apoapsis_in_km = result['apoapsis']['value']
                self.add_quantitative_value(planet_res, spacevoc.apoapsis, "KMT", apoapsis_in_km)

                diameter_in_km = result['diameter']['value']
                self.add_quantitative_value(planet_res, spacevoc.diameter, "KMT", diameter_in_km)

        # convert moon data
        wikidata_moons_path = args.source / "wikidata_moons.json"
        with open(wikidata_moons_path) as wikidata_moons_file:
            wikidata_moons = json.load(wikidata_moons_file)

            for result in wikidata_moons['results']['bindings']:
                moon_name = result['satelliteLabel']['value']
                moon_id = f"m_{slugify(moon_name)}"
                moon_res = space[moon_id]
                graph.add( (moon_res, RDF.type, spacevoc.Moon) )
                graph.add( (moon_res, RDFS.label, Literal(moon_name, lang="en")) )

                planet_name = result['planetLabel']['value']
                planet_id = f"p_{slugify(planet_name)}"
                planet_res = space[planet_id]

                graph.add( (moon_res, spacevoc.orbits, planet_res) )

                wikidata_url = result['satellite']['value']
                graph.add( (moon_res, schema.sameAs, URIRef(wikidata_url)) )

                self.add_image(result, 'satellite_image', moon_res)

                self.add_discoverer(result, moon_res)
                self.add_discovery_date(result, moon_res)

                if 'diameter' in result:
                    diameter_in_km = result['diameter']['value']
                    self.add_quantitative_value(moon_res, spacevoc.diameter, "KMT", diameter_in_km)
                if 'radius_sample' in result:
                    radius_in_km = result['radius_sample']['value']
                    self.add_quantitative_value(moon_res, spacevoc.radius, "KMT", radius_in_km)

        # create output
        graph.bind("space", space)
        graph.bind("spacevoc", spacevoc)
        graph.bind("schema", schema)
        graph.bind("wikidata", wikidata)

        with open(args.output, "w") as output_file:
            output_file.write(graph.serialize(format="turtle"))

parser = argparse.ArgumentParser(
    description="Convert the output of a specific query to Wikidata to RDF.")
parser.add_argument('--source',
                    default=Path('data/temp/'),
                    type=Path,
                    help="Path to the folder containing the source files. Default is `data/temp/`.")
parser.add_argument('--output',
                    help="Path to the Turtle output file",
                    type=Path,
                    default=Path('data/planets_and_satellites.ttl')
                    )
parser.add_argument('--base',
                    help="Base-URL for the output dataset.",
                    )
                    
args = parser.parse_args()
converter = SpaceConverter(args)
converter.convert()
