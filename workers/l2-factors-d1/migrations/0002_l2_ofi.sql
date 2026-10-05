-- 已上线的库补订单流不平衡列。D1 不支持 ADD COLUMN IF NOT EXISTS。
ALTER TABLE l2_factors ADD COLUMN l2_ofi REAL;
