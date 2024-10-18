from functools import lru_cache
import numpy as np
import pandas as pd
import talib as ta
from numba import jit

@jit(nopython=True)
def fast_k(rsi: np.ndarray, low: np.ndarray, high: np.ndarray, n: int) -> np.ndarray:
    """Calculate fast k stochastic of RSI."""
    return 100 * (rsi - low) / (high - low)

@lru_cache(maxsize=None)
def stoch_rsi(close: pd.Series, 
              length: int = 14, 
              k_period: int = 5, 
              d_period: int = 3) -> tuple[pd.Series, pd.Series]:
    """
    Calculates the Stochastic RSI of a price series.
    
    Parameters
    ----------
    close : pd.Series
        The closing price series.
    length : int, optional
        The lookback period for RSI calculation, by default 14.
    k_period : int, optional
        The smoothing period for %K, by default 5.
    d_period : int, optional
        The smoothing period for %D, by default 3.
        
    Returns
    -------
    fastk, fastd : tuple[pd.Series, pd.Series]
        The fast %K and %D stochastic series.
    """
    rsi_ = ta.RSI(close, timeperiod=length)
    rsi_low = rsi_.rolling(window=length).min()
    rsi_high = rsi_.rolling(window=length).max()

    fastk = pd.Series(fast_k(rsi_.values, rsi_low.values, rsi_high.values, len(close)), 
                      index=close.index)
    fastk = ta.SMA(fastk, timeperiod=k_period)
    
    fastd = ta.SMA(fastk, timeperiod=d_period)
    
    return fastk, fastd
