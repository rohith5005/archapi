import { Request, Response, NextFunction } from "express";
import { userService } from "../services/user.service";

export const userController = {
  async getById(req: Request, res: Response, next: NextFunction) {
    try {
      const user = await userService.getById(req.params.id);
      return res.status(200).json({ data: user });
    } catch (error) {
      return next(error);
    }
  },
};
