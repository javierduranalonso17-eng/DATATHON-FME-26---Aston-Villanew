"""
agent.py
Plantilla oficial de l'agent de control per al repte de la bateria de UPC Sostenible.
Datathon 2026.
"""

# import joblib  # Descomenteu si utilitzeu models serialitzats (.pkl)

class BatteryAgent:
    def __init__(self):
        """Inicialització de l'agent.
        S'executa una sola vegada a l'inici del període d'avaluació.
        Permet carregar models predictius o definir llindars d'operació.
        """
        # Paràmetres d'operació de la política de referència
        self.llindar_preu_carrega = 0.08      # €/kWh
        self.llindar_preu_descarrega = 0.16   # €/kWh
        self.potencia_nominal_kw = 500.0      # Potència màxima de l'inversor (kW)

        # Memòria històrica d'hores passades (permet consultar el passat dins de la simulació):
        # self.historial = []

    def act(self, obs: dict) -> float:
        """Determina la consigna de potència activa de la bateria per a l'hora actual.

        Paràmetres:
        -----------
        obs : dict amb les variables d'estat disponibles a l'hora actual:
            - "timestamp": pd.Timestamp amb la data i hora d'avaluació.
            - "hour": int de 0 a 23 (hora del dia).
            - "day_of_week": int de 0 (dilluns) a 6 (diumenge).
            - "soc_kwh": float amb l'energia emmagatzemada actual (0.0 a 2.000.0 kWh).
            - "soc_pct": float amb l'estat de càrrega relatiu [0.0, 1.0].
            - "preu_actual": float amb el preu del PVPC d'aquesta hora (€/kWh).
            - "co2_actual": float amb la intensitat de CO2 peninsular (kg CO2/kWh).
            - "preus_properes_24h": llista de preus horaris de les properes 24 hores (€/kWh).
            - "co2_properes_24h": llista de factors d'emissió de CO2 de les properes 24 hores (kg/kWh).
            - "noves_dades_5min": dades mesurades pels sensors en la darrera hora transcorreguda.

        Retorna:
        --------
        float : Consigna de potència activa en kW:
            > 0  -> Càrrega d'energia des de la xarxa interna (fins a +500.0 kW).
            < 0  -> Descàrrega d'energia cap al campus (fins a -500.0 kW).
            = 0  -> Bateria en mode d'espera (0.0 kW).
        """
        # =====================================================================
        # CARGAR CUANDO LA ENERGÍA ES "BARATA Y DESCARGAR
        # CUANDO ES "CARA", COMPARANDO CADA HORA CON LAS PRÓXIMAS 24 HORAS.
        # =====================================================================

        # ====== BATERÍA ======
        capacidad = 2000.0          # kWh
        potencia = 500.0            # kW (carga y descarga máximas)
        rendimiento = 0.9           # pérdida de energía al cargar o descargar
        bateria = obs["soc_kwh"]        # energía guardada actual (kWh)

        # Hacer una lista con los valores de las próximas horas
        # Número alto = hora mala para consumir de la red (cara o contaminante).

        valores = []
        for i in range(len(obs["preus_properes_24h"])):
            co2_hora = obs["co2_properes_24h"][i]
            precio_hora = obs["preus_properes_24h"][i]
            valor = 0.7 * co2_hora / 0.0718 + 0.3 * precio_hora / 0.1188    # relación nota actual-agente
            valores.append(valor)   #crea una lista con las notas 24 - i horas
        valor_ahora = valores[0]

        #   Fijar los umbrales de "barato" y "caro"
        #   Ordenamos los valores de menor a mayor y cogemos:
        #   - El que deja al 30 % de las horas por debajo  -> umbral de barato -> Mejor consumir
        #   - El que deja al 70 % de las horas por debajo  -> umbral de caro
        ordenados = sorted(valores)
        posicion_barato = int(0.30 * (len(ordenados) - 1))
        posicion_caro = int(0.70 * (len(ordenados) - 1))
        umbral_barato = ordenados[posicion_barato]
        umbral_caro = ordenados[posicion_caro]
        valor_maximo = max(valores)

        #   Qué hacer en esta hora, la actual
        consigna = 0.0    # por defecto, no hacer nada

        # Cargar: la hora actual es barata y más tarde habrá una hora cara
        # que compense la pérdida del 10 % del ciclo.
        if valor_ahora <= umbral_barato and valor_maximo * 0.9 > valor_ahora:
            consigna = potencia
        # Descargar: la hora actual es cara.
        elif valor_ahora >= umbral_caro and len(valores) >= 2:
            consigna = -potencia

        # --- Paso 4: no pedir nunca más de lo que la batería puede dar ---
        max_carga = (capacidad - bateria) / rendimiento * 0.999 
        max_descarga = bateria * rendimiento * 0.999
        if consigna > max_carga:
            consigna = max_carga
        if consigna < -max_descarga:
            consigna = -max_descarga

        # =====================================================================

        # Clamping de seguretat física per evitar infraccions de retallada (clipping):
        # Capacitat màxima: 2.000 kWh, Rendiment: sqrt(0.90) ~= 0.9487
        soc_kwh = float(obs["soc_kwh"])
        rendiment_eta = 0.9487
        max_carrega = min(self.potencia_nominal_kw, (2000.0 - soc_kwh) / rendiment_eta)
        max_descarrega = min(self.potencia_nominal_kw, soc_kwh * rendiment_eta)

        return float(max(-max_descarrega, min(max_carrega, consigna)))