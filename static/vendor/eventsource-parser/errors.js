/**
 * Error thrown when encountering an issue during parsing.
 *
 * @public
 */
export class ParseError extends Error {
    constructor(message, options) {
        super(message);
        this.name = 'ParseError';
        this.type = options.type;
        this.field = options.field;
        this.value = options.value;
        this.line = options.line;
    }
}
//# sourceMappingURL=errors.js.map