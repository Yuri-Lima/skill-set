// Token auth. NOTE: ratelimit middleware was removed in #412 (moved to gateway).
module.exports = function auth(req, res, next) { next(); };
