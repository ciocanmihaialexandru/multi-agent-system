"""
Tool implementations — funcțiile efective ale tool-urilor.

Convenție: toate tools primesc params cu `input_dfs` (lista de DataFrames) + parametri specifici.
"""
import pandas as pd

from .registry import register_tool
from .params import JoinDataParams, FilterDataParams


@register_tool
def join_data(params: JoinDataParams) -> pd.DataFrame:
    """
    Combină două DataFrames pe baza unei chei comune (join).
    Suportă inner, left, right, outer join.

    TODO: Implementează folosind pandas merge().

    Args:
        params.input_dfs: [left_df, right_df]
        params.left_key: coloana cheie din primul DataFrame
        params.right_key: coloana cheie din al doilea DataFrame
        params.how: tipul de join

    Returns:
        DataFrame rezultat după join
    """
    # TODO: implementează
    # left_df = params.input_dfs[0]
    # right_df = params.input_dfs[1]
    # return pd.merge(left_df, right_df, left_on=params.left_key, right_on=params.right_key, how=params.how)
    
    # Avem nevoie de exact două DataFrames pentru un join.
    if len(params.input_dfs) < 2:
        raise ValueError(
            f"join_data are nevoie de 2 DataFrames, am primit {len(params.input_dfs)}"
        )

    left_df, right_df = params.input_dfs[0], params.input_dfs[1]

    # Verificăm că cheile există, ca să dăm o eroare clară (nu un KeyError criptic).
    if params.left_key not in left_df.columns:
        raise KeyError(
            f"Cheia '{params.left_key}' lipsește din DataFrame-ul stâng. "
            f"Coloane: {list(left_df.columns)}"
        )
    if params.right_key not in right_df.columns:
        raise KeyError(
            f"Cheia '{params.right_key}' lipsește din DataFrame-ul drept. "
            f"Coloane: {list(right_df.columns)}"
        )

    # Join-ul propriu-zis. left_on/right_on permit chei cu nume diferite
    # în cele două tabele (ex: 'castigator_cui' vs 'cui').
    return pd.merge(
        left_df,
        right_df,
        left_on=params.left_key,
        right_on=params.right_key,
        how=params.how,
    )



@register_tool
def filter_data(params: FilterDataParams) -> pd.DataFrame:
    """
    Filtrează un DataFrame pe baza unei condiții.
    Suportă operatori: ==, !=, >, <, >=, <=, contains.

    TODO: Implementează folosind pandas boolean indexing.

    Args:
        params.input_dfs: [df]
        params.column: coloana pe care se aplică filtrul
        params.operator: operatorul de comparație
        params.value: valoarea pentru comparație

    Returns:
        DataFrame filtrat
    """
    # TODO: implementează
    # df = params.input_dfs[0]
    # col = df[params.column]
    # if params.operator == "==":
    #     mask = col == params.value
    # elif params.operator == "contains":
    #     mask = col.astype(str).str.contains(params.value, case=False, na=False)
    # ...
    # return df[mask]
    df = params.input_dfs[0]
    column = params.column
    operator = params.operator
    value = params.value

    # Coloană inexistentă → eroare clară (altfel pandas dă KeyError criptic).
    if column not in df.columns:
        raise KeyError(
            f"Coloana '{column}' nu există. Disponibile: {list(df.columns)}"
        )

    col = df[column]

    # Construim "masca" booleană (True = rândul rămâne) în funcție de operator.
    if operator == "contains":
        # Căutare text, case-insensitive; na=False scoate NaN-urile din rezultat.
        mask = col.astype(str).str.contains(value, case=False, na=False)

    elif operator in (">", "<", ">=", "<="):
        # Operatori numerici: convertim coloana și valoarea la număr.
        # errors="coerce" → ce nu-i număr devine NaN (și pică automat din filtru).
        numeric_col = pd.to_numeric(col, errors="coerce")
        numeric_val = float(value)
        comparisons = {
            ">": numeric_col > numeric_val,
            "<": numeric_col < numeric_val,
            ">=": numeric_col >= numeric_val,
            "<=": numeric_col <= numeric_val,
        }
        mask = comparisons[operator]

    else:  # "==" sau "!="
        # Egalitate: încercăm întâi numeric (ca "100" == 100), altfel pe text.
        numeric_val = pd.to_numeric(value, errors="coerce")
        numeric_col = pd.to_numeric(col, errors="coerce")
        if pd.notna(numeric_val) and numeric_col.notna().any():
            base = numeric_col == numeric_val
        else:
            base = col.astype(str) == value
        mask = base if operator == "==" else ~base

    return df[mask]
