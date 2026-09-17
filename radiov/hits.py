from __future__ import annotations

# Listas de éxitos curadas por épocas. Son el "punto de entrada": a partir de cada
# canción/artista el agente expande con artistas relacionados y sus temas más conocidos,
# de modo que el catálogo crece de forma continua (no es una lista cerrada de artistas).

ES_HITS: dict[str, list[tuple[str, str]]] = {
    "60s-70s": [
        ("Julio Iglesias", "Me va, me va"), ("Raphael", "Mi gran noche"),
        ("Peret", "Borriquito"), ("Los Brincos", "Flamenco"),
        ("Nino Bravo", "Te quiero, te quiero"), ("Los Módulos", "Todo tiene su edad"),
        ("Camilo Sesto", "Fresa salvaje"), ("Karina", "En tu fiesta me colé"),
        ("Juan Pardo", "Mi carro"), ("Rocío Dúrcal", "Amor eterno"),
        ("Emilio José", "Chiquilla"), ("Manolo Escobar", "El porompompero"),
        ("Mocedades", "Eres tú"), ("Vicky Carr", "Hoy quiero confesar"),
        ("Los Bravos", "Black Is Black"), ("Miguel Ríos", "Santa Lucía"),
        ("Fórmula V", "Cuéntame"), ("Pop-Tops", "Mamy Blue"),
        ("La Banda del Parque", "Miénteme"), ("Jeanette", "Porque te vas"),
    ],
    "80s": [
        ("Mecano", "Hijo de la luna"), ("Mecano", "Mujeres"), ("Mecano", "Me cuesta tanto olvidarte"),
        ("Alaska y Dinarama", "Ni tú ni nadie"), ("Los Secretos", "Déjame"),
        ("Nacha Pop", "Chica de ayer"), ("Hombres G", "Devuélveme a mi chica"),
        ("Hombres G", "Marta tiene un marcapasos"), ("La Oreja de Van Gogh", "El 28"),
        ("Loquillo", "Feo, fuerte y formal"), ("Gabinete Caligari", "Que Dios reparta suerte"),
        ("Zombies", "Groenlandia"), ("Radio Futura", "La negra Flor"),
        ("Duncan Dhu", "Cien gaviotas"),
        ("La Unión", "Lobo hombre en París"), ("Mecano", "Hoy no me puedo levantar"),
        ("Ilegales", "Hola, ¿qué tal?"), ("Álex y Christina", "Chu chu"),
        ("El Último de la Fila", "El loco de la colina"), ("Obús", "Dime dónde está el amor"),
        ("Whitesnake", "Still of the Night"), ("Alaska", "Quién eres tú"),
    ],
    "90s": [
        ("Alejandro Sanz", "Corazón partío"), ("Alejandro Sanz", "Amante mía"),
        ("Maná", "En el muelle de San Blas"), ("Jarabe de Palo", "La Flaca"),
        ("La Oreja de Van Gogh", "Cuéntame al oído"), ("Los del Río", "Macarena"),
        ("Gipsy Kings", "Djobi Djoba"), ("Marta Sánchez", "Desconocidos"),
        ("Malú", "Te conozco desde siempre"), ("Presuntos Implicados", "Alma de blues"),
        ("Mecano", "Una rosa es una rosa"), ("Olive", "Me enamora"),
        ("Amistades Peligrosas", "Me haces tanto bien"), ("Sandra", "Quién te crees"),
        ("Sin Bandera", "Entra en mi vida"), ("Alejandra Guzmán", "Mala hierba"),
        ("Chayanne", "Tiempo de vals"), ("Ricky Martin", "María"),
        ("Enrique Iglesias", "Por amarte"), ("Marcos Llunas", "Un tipo corriente"),
        ("Kiko Veneno", "Volando voy"), ("La Cabra Mecánica", "Para no dormir"),
        ("Nacha Pop", "Chica de ayer"), ("Luz Casal", "Piensa en mí"),
    ],
    "00s": [
        ("La Oreja de Van Gogh", "Rosas"), ("Estopa", "La raja de tu falda"),
        ("El Canto del Loco", "Besos"), ("Amaral", "Sin ti no soy nada"),
        ("David Bisbal", "Ave María"), ("Camela", "Suspiros"),
        ("Marea", "Ciudad de los árboles"), ("Shakira", "La Tortura"),
        ("Juanes", "La Camisa Negra"), ("Maná", "Labios Compartidos"),
        ("Maldita Nerea", "El secreto de las tortugas"), ("Nena Daconte", "Idiota"),
        ("Pereza", "Al amanecer"), ("Mägo de Oz", "Fiesta pagana"),
        ("Estopa", "Como Camarón"), ("Deluxe", "La respuesta"),
        ("El Canto del Loco", "La madre de José"), ("Marta Valverde", "No sabes qué te espera"),
        ("La Quinta Estación", "El sol no regresa"), ("Mando", "Dame la razón"),
        ("Antonio José", "El mundo a tus pies"), ("Juanes", "Me enamora"),
    ],
    "10s": [
        ("Luis Fonsi", "Despacito"), ("Enrique Iglesias", "Bailando"),
        ("Shakira", "Waka Waka (This Time for Africa)"), ("Shakira", "La La La (Brazil 2014)"),
        ("Danny Ocean", "Me Rehúso"), ("Maluma", "Felices los 4"),
        ("Camila", "Mientes"), ("Jesse & Joy", "¡Corre!"),
        ("Natalia Lafourcade", "Hasta la Raíz"), ("Daddy Yankee", "Gasolina"),
        ("Don Omar", "Danza Kuduro"), ("J Balvin", "Mi Gente"),
        ("Fonsi", "Échame la culpa"), ("Carlos Vives", "La Bicicleta"),
    ],
    "20s": [
        ("Bad Bunny", "Tití Me Preguntó"), ("Bad Bunny", "Moscow Mule"),
        ("Bad Bunny", "DTMF"), ("KAROL G", "Tusa"), ("KAROL G", "Bichota"),
        ("KAROL G", "Si Antes Te Hubiera Conocido"), ("Rauw Alejandro", "Todo de Ti"),
        ("Quevedo", "BZRP Music Sessions, Vol. 52"), ("Feid", "La Bachata"),
        ("Rosalía", "DESPECHÁ"), ("Myke Towers", "La Vecina"),
        ("Rauw Alejandro", "Punto 40"), ("Ana Mena", "Las 12"),
        ("Aitana", "Mon Amour"),
    ],
}

EN_HITS: dict[str, list[tuple[str, str]]] = {
    "80s": [
        ("Michael Jackson", "Billie Jean"), ("Michael Jackson", "Thriller"),
        ("Madonna", "Like a Prayer"), ("Queen", "Radio Ga Ga"),
        ("Bon Jovi", "Livin' on a Prayer"), ("A-ha", "Take on Me"),
        ("Prince", "Purple Rain"), ("AC/DC", "You Shook Me All Night Long"),
        ("Europe", "The Final Countdown"), ("Whitesnake", "Here I Go Again"),
    ],
    "90s": [
        ("Nirvana", "Smells Like Teen Spirit"), ("Backstreet Boys", "I Want It That Way"),
        ("Spice Girls", "Wannabe"), ("Britney Spears", "...Baby One More Time"),
        ("TLC", "Waterfalls"), ("Oasis", "Wonderwall"), ("Blur", "Song 2"),
        ("Ricky Martin", "Livin' la Vida Loca"), ("Shakira", "Whenever, Wherever"),
    ],
    "00s": [
        ("Rihanna", "Umbrella"), ("Beyoncé", "Crazy in Love"), ("Eminem", "Lose Yourself"),
        ("Coldplay", "Yellow"), ("Avril Lavigne", "Complicated"),
        ("The Black Eyed Peas", "I Gotta Feeling"), ("Lady Gaga", "Poker Face"),
        ("Justin Timberlake", "Cry Me a River"), ("Sixpence None the Richer", "Kiss Me"),
    ],
    "10s": [
        ("The Weeknd", "Blinding Lights"), ("Dua Lipa", "Don't Start Now"),
        ("Beyoncé", "Halo"), ("Ed Sheeran", "Shape of You"),
        ("Maroon 5", "Sugar"), ("Bruno Mars", "Just the Way You Are"),
        ("Adele", "Rolling in the Deep"), ("Billie Eilish", "Bad Guy"),
        ("Lady Gaga", "Shallow"), ("Taylor Swift", "Blank Space"),
    ],
}


def get_hits(lang: str = "es") -> list[tuple[str, str]]:
    """Devuelve la lista aplanada de (artista, título) de los éxitos de un idioma."""
    data = ES_HITS if lang == "es" else EN_HITS
    out: list[tuple[str, str]] = []
    for period in sorted(data.keys()):
        out.extend(data[period])
    return out
