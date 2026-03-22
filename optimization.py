from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, LpContinuous
from copper.models import CopperStock

def select_stocks_for_moyenne(target_moyenne=None, target_moyenne_nb=None):
    """
    Original function: Binary selection (all or nothing per stock)
    Used for initial auto-filtering
    """
    remaining_stocks = [s for s in CopperStock.query.all() if s.local_balance > 0]
    stock_vars = {s.id: LpVariable(f"stock{s.id}", cat=LpBinary) for s in remaining_stocks}

    prob = LpProblem("Stock_selection_for_Target_Moyenne", LpMinimize)

    # Calculate totals based on selected stocks
    total_unit_percent = lpSum(s.unit_percent * stock_vars[s.id] for s in remaining_stocks)
    total_t_unity = lpSum(s.t_unity * stock_vars[s.id] for s in remaining_stocks)
    total_balance = lpSum(s.local_balance * stock_vars[s.id] for s in remaining_stocks)

    # Objective: minimize absolute difference(s)
    objective_terms = []

    if target_moyenne:
        error_moyenne = LpVariable("error_moyenne", lowBound=0)
        prob += error_moyenne >= total_unit_percent - target_moyenne * total_balance
        prob += error_moyenne >= -(total_unit_percent - target_moyenne * total_balance)
        objective_terms.append(error_moyenne)

    if target_moyenne_nb:
        error_moyenne_nb = LpVariable("error_moyenne_nb", lowBound=0)
        prob += error_moyenne_nb >= total_t_unity - target_moyenne_nb * total_balance
        prob += error_moyenne_nb >= -(total_t_unity - target_moyenne_nb * total_balance)
        objective_terms.append(error_moyenne_nb)

    # Objective: minimize total error
    prob += lpSum(objective_terms)

    # Constraint: at least one stock must be selected
    prob += lpSum(stock_vars[s.id] for s in remaining_stocks) >= 2

    # Solve
    prob.solve()

    selected_stocks = [s for s in remaining_stocks if stock_vars[s.id].value() == 1]

    total_unit = sum(s.unit_percent for s in selected_stocks)
    total_tunity = sum(s.t_unity for s in selected_stocks)
    total_balance_val = sum(s.local_balance for s in selected_stocks)

    achieved_moyenne = total_unit / total_balance_val if total_balance_val else 0
    achieved_moyenne_nb = total_tunity / total_balance_val if total_balance_val else 0

    return selected_stocks, achieved_moyenne, achieved_moyenne_nb


def select_stocks_with_minimum_quantities(target_moyenne=None, target_moyenne_nb=None, minimum_quantities=None):
    """
    Advanced function: HYBRID selection (mix of binary and continuous)
    
    User says: "I want moyenne=45, BUT use at least 150kg from S1"
    
    This function RE-OPTIMIZES ALL stocks while respecting:
    1. The target moyenne (quality constraint)
    2. User's specified minimum quantities (continuous - may have decimals)
    3. Other stocks are BINARY (0 = don't use, 1 = use ALL available)
       → NO unnecessary decimals like 0.123kg or 1.945kg
    
    Args:
        target_moyenne: Target quality %
        target_moyenne_nb: Target secondary quality metric
        minimum_quantities: Dict {stock_id: minimum_kg}
                           Example: {1: 150, 2: 80}
                           Stocks WITH minimums: can have decimals (user specified)
                           Stocks WITHOUT minimums: binary only (0 or all, NO decimals)
    
    Returns:
        (selected_stocks_list, achieved_moyenne, achieved_moyenne_nb, quantities_dict)
    """
    remaining_stocks = [s for s in CopperStock.query.all() if s.local_balance > 0]
    
    if not remaining_stocks:
        return [], 0, 0, {}
    
    # ===== HYBRID APPROACH: Mix binary and continuous =====
    # User-specified stocks: CONTINUOUS (can have decimals since user knows)
    # Other stocks: BINARY (0 or 1, representing "all or nothing")
    stock_vars = {}
    
    for s in remaining_stocks:
        if minimum_quantities and s.id in minimum_quantities:
            # This stock has user-specified minimum quantity
            # Use CONTINUOUS: can be 150kg, 150.5kg, 150.9kg, etc.
            min_qty = minimum_quantities[s.id]
            stock_vars[s.id] = LpVariable(
                f"stock{s.id}",
                lowBound=min_qty,        # User's minimum (exact)
                upBound=min_qty, # min_quantity or Maximum available(when appropriate)
                cat=LpContinuous         # Decimals OK (user specified)
            )
        else:
            # This stock is NOT specified by user
            # Use BINARY: either 0 (don't use) or 1 (use all available)
            # Result will be: 0 * s.local_balance = 0 kg
            #            or: 1 * s.local_balance = ALL kg (no decimals!)
            stock_vars[s.id] = LpVariable(
                f"stock{s.id}",
                cat=LpBinary  # 0 or 1 only - NO decimals!
            )
    
    prob = LpProblem("Stock_selection_with_minimums_hybrid", LpMinimize)
    
    # ===== Calculate totals BASED ON quantities PuLP chooses =====
    # Extract percentage first: percentage = unit_percent / local_balance
    # For continuous variables: percentage × user_qty
    # For binary variables: percentage × (0_or_1 × local_balance)
    total_unit_percent = lpSum(
        (s.unit_percent / s.local_balance if s.local_balance > 0 else 0) * (
            stock_vars[s.id] if (minimum_quantities and s.id in minimum_quantities)
            else stock_vars[s.id] * s.local_balance
        )
        for s in remaining_stocks
    )
    
    total_t_unity = lpSum(
        (s.t_unity / s.local_balance if s.local_balance > 0 else 0) * (
            stock_vars[s.id] if (minimum_quantities and s.id in minimum_quantities)
            else stock_vars[s.id] * s.local_balance
        )
        for s in remaining_stocks
    )
    
    total_balance = lpSum(
        (
            stock_vars[s.id] if (minimum_quantities and s.id in minimum_quantities)
            else stock_vars[s.id] * s.local_balance
        )
        for s in remaining_stocks
    )
    
    # ===== SAME ERROR MINIMIZATION AS ORIGINAL =====
    objective_terms = []
    
    if target_moyenne:
        error_moyenne = LpVariable("error_moyenne", lowBound=0)
        prob += error_moyenne >= total_unit_percent - target_moyenne * total_balance
        prob += error_moyenne >= -(total_unit_percent - target_moyenne * total_balance)
        objective_terms.append(error_moyenne)
    
    if target_moyenne_nb:
        error_moyenne_nb = LpVariable("error_moyenne_nb", lowBound=0)
        prob += error_moyenne_nb >= total_t_unity - target_moyenne_nb * total_balance
        prob += error_moyenne_nb >= -(total_t_unity - target_moyenne_nb * total_balance)
        objective_terms.append(error_moyenne_nb)
    
    # ===== CONSTRAINT: Total quantity must be positive =====
    prob += total_balance >= 1
    
    # ===== OBJECTIVE: Minimize error =====
    if objective_terms:
        prob += lpSum(objective_terms)
    else:
        # If no target specified, just minimize total used (prefer smaller quantities)
        prob += total_balance
    
    # Solve
    prob.solve()
    
    # ===== Extract results =====
    selected_stocks = []
    quantities = {}
    
    for s in remaining_stocks:
        var_value = stock_vars[s.id].value()
        
        if var_value is None:
            continue
            
        if minimum_quantities and s.id in minimum_quantities:
            # Continuous variable: use value directly (already in kg)
            qty = var_value
        else:
            # Binary variable: multiply by available balance
            # If value=1, qty = s.local_balance (use all)
            # If value=0, qty = 0 (use none)
            qty = var_value * s.local_balance
        
        if qty and qty > 0.01:  # More than 0.01kg
            selected_stocks.append(s)
            quantities[s.id] = qty
    
    # Calculate achieved quality metrics
    # Formula: percentage = unit_percent / local_balance
    # Then: contribution = percentage * quantity_used
    # Moyenne = sum(contributions) / sum(quantities)
    total_unit = sum((s.unit_percent / s.local_balance if s.local_balance > 0 else 0) * quantities.get(s.id, 0) for s in selected_stocks)
    total_tunity = sum((s.t_unity / s.local_balance if s.local_balance > 0 else 0) * quantities.get(s.id, 0) for s in selected_stocks)
    total_qty = sum(quantities.get(s.id, 0) for s in selected_stocks)
    
    achieved_moyenne = total_unit / total_qty if total_qty else 0
    achieved_moyenne_nb = total_tunity / total_qty if total_qty else 0
    
    return selected_stocks, achieved_moyenne, achieved_moyenne_nb, quantities
