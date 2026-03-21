"""
Cassiterite Optimization Functions
Follows the same hybrid binary/continuous pattern as copper
"""
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, LpContinuous
from cassiterite.models import CassiteriteStock


def select_stocks_for_average_quality(target_moyenne=None):
    """
    Binary selection: Select stocks to achieve target average quality.
    Each stock is either selected (1) or not (0) - takes ALL available if selected.
    
    Used in STEP 1 of optimization.
    
    Args:
        target_moyenne: Target average purity/quality %
    
    Returns:
        (selected_stocks_list, achieved_moyenne)
    """
    remaining_stocks = [s for s in CassiteriteStock.query.all() if s.local_balance > 0]
    
    if not remaining_stocks:
        return [], 0
    
    # Binary: each stock is either selected (1) or not (0)
    stock_vars = {s.id: LpVariable(f"stock{s.id}", cat=LpBinary) for s in remaining_stocks}
    
    prob = LpProblem("Cassiterite_Stock_Selection_Binary", LpMinimize)
    
    # Total unit contribution (quality * quantity)
    total_unit = lpSum(
        s.unit_percent * stock_vars[s.id] 
        for s in remaining_stocks
    )
    
    # Total quantity
    total_qty = lpSum(
        s.local_balance * stock_vars[s.id] 
        for s in remaining_stocks
    )
    
    # Objective: minimize error from target moyenne
    if target_moyenne:
        error = LpVariable("error_moyenne", lowBound=0)
        prob += error >= total_unit - (target_moyenne * total_qty)
        prob += error >= -(total_unit - (target_moyenne * total_qty))
        prob += error
    else:
        # If no target, just maximize quality
        prob += total_unit
    
    # At least one stock must be selected
    prob += lpSum(stock_vars[s.id] for s in remaining_stocks) >= 1
    
    # Solve
    prob.solve()
    
    # Extract selected stocks
    selected_stocks = [s for s in remaining_stocks if stock_vars[s.id].value() == 1]
    
    # Calculate achieved moyenne
    total_unit_val = sum(s.unit_percent for s in selected_stocks)
    total_qty_val = sum(s.local_balance for s in selected_stocks)
    achieved_moyenne = total_unit_val / total_qty_val if total_qty_val > 0 else 0
    
    return selected_stocks, achieved_moyenne


def select_stocks_with_minimum_quantities_cassiterite(target_moyenne=None, minimum_quantities=None):
    """
    Hybrid selection: BINARY for unrestricted stocks, CONTINUOUS for user-specified quantities.
    
    User specifies: "I want 150kg from stock S1, 80kg from S2, and optimize the rest"
    
    Used in STEP 3 of optimization (recalculate with user adjustments).
    
    Args:
        target_moyenne: Target average quality %
        minimum_quantities: Dict {stock_id: kg} of user-specified quantities
                           Stocks with values: CONTINUOUS (can have decimals)
                           Stocks without values: BINARY (0 or all available)
    
    Returns:
        (selected_stocks_list, achieved_moyenne, quantities_dict)
    """
    remaining_stocks = [s for s in CassiteriteStock.query.all() if s.local_balance > 0]
    
    if not remaining_stocks:
        return [], 0, {}
    
    # Hybrid approach: mix binary and continuous
    stock_vars = {}
    
    for s in remaining_stocks:
        if minimum_quantities and s.id in minimum_quantities:
            # User specified a quantity: CONTINUOUS (can be 150.5kg, not just 0 or all)
            min_qty = minimum_quantities[s.id]
            stock_vars[s.id] = LpVariable(
                f"stock{s.id}",
                lowBound=min_qty,
                upBound=s.local_balance,
                cat=LpContinuous  # Decimals allowed
            )
        else:
            # User didn't specify: BINARY (0 or use all available)
            stock_vars[s.id] = LpVariable(
                f"stock{s.id}",
                cat=LpBinary  # 0 or 1 only
            )
    
    prob = LpProblem("Cassiterite_Stock_Selection_Hybrid", LpMinimize)
    
    # Calculate totals
    total_unit = lpSum(
        s.unit_percent / s.local_balance * (
            stock_vars[s.id] if (minimum_quantities and s.id in minimum_quantities)
            else stock_vars[s.id] * s.local_balance
        )
        for s in remaining_stocks if s.local_balance > 0
    )
    
    total_qty = lpSum(
        (
            stock_vars[s.id] if (minimum_quantities and s.id in minimum_quantities)
            else stock_vars[s.id] * s.local_balance
        )
        for s in remaining_stocks
    )
    
    # Objective: minimize error from target moyenne
    if target_moyenne:
        error = LpVariable("error_moyenne", lowBound=0)
        prob += error >= total_unit - (target_moyenne * total_qty)
        prob += error >= -(total_unit - (target_moyenne * total_qty))
        prob += error
    else:
        prob += total_qty
    
    # Total quantity must be positive
    prob += total_qty >= 1
    
    # Solve
    prob.solve()
    
    # Extract results
    selected_stocks = []
    quantities = {}
    
    for s in remaining_stocks:
        var_value = stock_vars[s.id].value()
        
        if var_value is None:
            continue
        
        if minimum_quantities and s.id in minimum_quantities:
            # Continuous: use value directly (already in kg)
            qty = var_value
        else:
            # Binary: multiply by available balance
            qty = var_value * s.local_balance
        
        if qty and qty > 0.01:
            selected_stocks.append(s)
            quantities[s.id] = qty
    
    # Calculate achieved moyenne
    total_unit_val = sum(
        (s.unit_percent / s.local_balance if s.local_balance > 0 else 0) * quantities.get(s.id, 0)
        for s in selected_stocks
    )
    total_qty_val = sum(quantities.get(s.id, 0) for s in selected_stocks)
    achieved_moyenne = total_unit_val / total_qty_val if total_qty_val > 0 else 0
    
    return selected_stocks, achieved_moyenne, quantities
